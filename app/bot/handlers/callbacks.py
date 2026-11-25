"""
app/bot/handlers/callbacks.py

Simplified, robust callback query handlers for Kayi Image Compressor.
Wires Auto Compress, Set Target Size, Advanced Settings, and 1-tap Retries.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from aiogram import Router, F, Bot
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery

from app.bot.keyboards.menus import (
    build_welcome_keyboard,
    build_help_keyboard,
    build_back_keyboard,
    build_image_options_keyboard,
    build_target_size_keyboard,
    build_advanced_settings_keyboard,
    build_result_keyboard,
)
from app.bot.messages.texts import (
    PROCESSING_TEXT,
    SESSION_EXPIRED_TEXT,
    HELP_TEXT,
)
from app.bot.middlewares.fsub import (
    check_channel_membership,
    get_and_clear_pending_start_param,
)
from app.compression.engine import run_compression_isolated, CompressionResult
from app.compression.formats import FORMAT_EXTENSIONS
from app.compression.presets import CompressionRequest, Preset
from app.services.cleanup import make_temp_path
from app.services.sessions import SessionStore, UserSession

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


def _format_advanced_text(session: UserSession) -> str:
    fmt_display = session.selected_format or f"Keep Original ({session.input_format})"
    preset_names = {
        "best_quality": "Best Quality",
        "balanced": "Balanced",
        "smallest": "Smallest File",
        "lossless": "Lossless",
    }
    preset_display = preset_names.get(session.selected_preset, "Balanced")
    meta_display = "Remove EXIF (Private)" if session.strip_metadata else "Preserve EXIF"

    if session.dimension_mode == "auto":
        dims_display = "Automatic (Adaptive)"
    elif session.dimension_mode == "100":
        dims_display = "100% (Original)"
    elif session.dimension_mode in ("75", "50", "25"):
        dims_display = f"{session.dimension_mode}% Scale"
    elif session.exact_width > 0 and session.exact_height > 0:
        dims_display = f"Exact {session.exact_width}×{session.exact_height}"
    elif session.max_width > 0 or session.max_height > 0:
        dims_display = f"Max {session.max_width or '∞'}×{session.max_height or '∞'}"
    else:
        dims_display = "Custom"

    return (
        "<b>⚙️ Advanced Settings</b>\n\n"
        f"• <b>Quality:</b> <code>{preset_display}</code>\n"
        f"• <b>Format:</b> <code>{fmt_display}</code>\n"
        f"• <b>Dimensions:</b> <code>{dims_display}</code>\n"
        f"• <b>Metadata:</b> <code>{meta_display}</code>\n\n"
        "<i>Tap any option to toggle. Tap Apply Settings when ready:</i>"
    )


async def _execute_compression_job(
    callback: CallbackQuery,
    session: UserSession,
    sessions: SessionStore,
    req: CompressionRequest,
    config: Any,
) -> None:
    """Helper to run compression job with in-flight protection and error handling."""
    if session.in_flight:
        await callback.answer("⏳ Processing is already in progress...", show_alert=True)
        return

    session.in_flight = True
    session.state = "processing"

    status_msg = await callback.message.edit_text(PROCESSING_TEXT, parse_mode=ParseMode.HTML)

    try:
        res: CompressionResult = await run_compression_isolated(
            req, timeout_seconds=config.processing_timeout_seconds
        )
        session.in_flight = False

        if not res.success and res.error:
            session.state = "error"
            await status_msg.edit_text(f"❌ <b>Error:</b> {res.error}", parse_mode=ParseMode.HTML)
            return

        session.state = "done"
        session.output_file_path = res.output_path
        session.output_format = res.stats.output_format if res.stats else ""
        session.output_size = res.stats.output_bytes if res.stats else 0

        from app.bot.handlers.compress import deliver_compression_result
        try:
            await status_msg.delete()
        except Exception:
            pass

        await deliver_compression_result(callback.message, session, res, config)

    except asyncio.TimeoutError:
        session.in_flight = False
        session.state = "error"
        await status_msg.edit_text(
            "⏱ <b>Processing Timeout</b>\n\nJob exceeded deadline and worker was safely terminated.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        session.in_flight = False
        session.state = "error"
        logger.exception("Compression job exception: %s", e)
        await status_msg.edit_text(f"❌ <b>Execution Error:</b> {e}", parse_mode=ParseMode.HTML)


# ==============================================================================
# FSUB VERIFICATION
# ==============================================================================

@router.callback_query(F.data == "fsub:verify")
async def cb_fsub_verify(callback: CallbackQuery, config: Any, bot: Bot | None = None) -> None:
    if bot is None:
        bot = callback.bot
    user_id = callback.from_user.id

    await callback.answer("Checking channel membership...")

    is_member, status = await check_channel_membership(
        bot=bot,
        user_id=user_id,
        channel=config.fsub_channel,
        bypass_cache=True,
        timeout=config.fsub_timeout,
    )

    if is_member:
        pending_param = get_and_clear_pending_start_param(user_id)
        if pending_param == "help":
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text=HELP_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=build_help_keyboard(),
                disable_web_page_preview=True,
            )
            return

        try:
            await callback.message.delete()
        except Exception:
            pass

        from app.bot.handlers.start import send_welcome_screen
        await send_welcome_screen(callback.message, config)
    else:
        if status in ("left", "kicked") or (status == "restricted" and not is_member):
            await callback.answer(
                f"You haven't joined {config.fsub_channel} yet. Please join the channel and tap I've Joined.",
                show_alert=True,
            )
        else:
            await callback.answer(
                "Membership check unavailable right now. Please try again shortly.",
                show_alert=True,
            )


# ==============================================================================
# NAVIGATION & CANCELLATION
# ==============================================================================

@router.callback_query(F.data == "compress:start")
async def cb_compress_start(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "<b>Ready to Compress</b>\n\n"
        "Send any photo or document image (JPEG, PNG, or WebP) to begin.",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("comp:back_main:"))
async def cb_back_main(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    from app.bot.handlers.compress import format_bytes, IMAGE_CARD_TEMPLATE
    w, h = session.input_dimensions
    card_text = IMAGE_CARD_TEMPLATE.format(
        fmt=session.input_format,
        size=format_bytes(session.input_file_size),
        dimensions=f"{w}×{h}",
        suggestion="",
    )
    await callback.message.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=build_image_options_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("comp:cancel:"))
async def cb_cancel(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    sessions.delete(session_id)
    await callback.message.edit_text("✦ <i>Compression cancelled. Send another image anytime.</i>", parse_mode=ParseMode.HTML)
    await callback.answer()


# ==============================================================================
# PRIMARY OPTION 1: AUTO COMPRESS
# ==============================================================================

@router.callback_query(F.data.startswith("comp:auto:"))
async def cb_auto(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    session.last_mode = "auto"
    session.last_preset = session.selected_preset

    out_fmt = session.selected_format or session.input_format
    out_ext = FORMAT_EXTENSIONS.get(out_fmt, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    preset_enum = Preset(session.selected_preset)
    is_lossless = (session.selected_preset == "lossless")
    allow_resize = (session.scale_percent < 0.99 or session.exact_width > 0 or session.max_width > 0)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        preset=preset_enum,
        output_format=session.selected_format,
        scale_percent=session.scale_percent,
        exact_width=session.exact_width,
        exact_height=session.exact_height,
        max_width=session.max_width,
        max_height=session.max_height,
        fit_mode=session.fit_mode,
        strip_metadata=session.strip_metadata,
        lossless=is_lossless,
        allow_resize=allow_resize,
    )
    await callback.answer()
    await _execute_compression_job(callback, session, sessions, req, config)


# ==============================================================================
# PRIMARY OPTION 2: SET TARGET SIZE
# ==============================================================================

@router.callback_query(F.data.startswith("comp:menu_target:"))
async def cb_menu_target(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    text = (
        "<b>🎯 Set Target File Size</b>\n\n"
        "Choose a target file size. Quality and proportional scaling will be automatically calibrated:"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_target_size_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("comp:target:"))
async def cb_target_preset(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    parts = callback.data.split(":")
    kb_str = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    if kb_str == "custom":
        session.state = "waiting_target_input"
        await callback.message.edit_text(
            "<b>Enter Custom Target Size</b>\n\n"
            "Send your desired file size in KB or MB (e.g. <code>40 KB</code> or <code>1.5 MB</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=build_back_keyboard(f"comp:menu_target:{session_id}"),
        )
        await callback.answer()
        return

    kb_val = int(kb_str)
    session.last_mode = "target"
    session.last_target_kb = kb_val

    out_fmt = session.selected_format or session.input_format
    out_ext = FORMAT_EXTENSIONS.get(out_fmt, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    # Automatic dimensions permits adaptive resizing; explicit dimensions lock resizing
    allow_downscale = (session.dimension_mode == "auto")

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        target_bytes=kb_val * 1024,
        output_format=session.selected_format,
        scale_percent=session.scale_percent,
        exact_width=session.exact_width,
        exact_height=session.exact_height,
        max_width=session.max_width,
        max_height=session.max_height,
        fit_mode=session.fit_mode,
        allow_resize=allow_downscale,
        strip_metadata=session.strip_metadata,
    )
    await callback.answer()
    await _execute_compression_job(callback, session, sessions, req, config)


# ==============================================================================
# PRIMARY OPTION 3: ADVANCED SETTINGS
# ==============================================================================

@router.callback_query(F.data.startswith("comp:menu_adv:"))
async def cb_menu_adv(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    text = _format_advanced_text(session)
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_advanced_settings_keyboard(session))
    await callback.answer()


@router.callback_query(F.data.startswith("adv:preset:"))
async def cb_adv_preset(callback: CallbackQuery, sessions: SessionStore) -> None:
    parts = callback.data.split(":")
    preset_name = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired.", show_alert=True)
        return

    session.selected_preset = preset_name
    text = _format_advanced_text(session)
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_advanced_settings_keyboard(session))
    await callback.answer("Preset updated")


@router.callback_query(F.data.startswith("adv:fmt:"))
async def cb_adv_fmt(callback: CallbackQuery, sessions: SessionStore) -> None:
    parts = callback.data.split(":")
    fmt_target = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired.", show_alert=True)
        return

    session.selected_format = "" if fmt_target == "ORIGINAL" else fmt_target
    text = _format_advanced_text(session)
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_advanced_settings_keyboard(session))
    await callback.answer("Format updated")


@router.callback_query(F.data.startswith("adv:dim:"))
async def cb_adv_dim(callback: CallbackQuery, sessions: SessionStore) -> None:
    parts = callback.data.split(":")
    dim_mode = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired.", show_alert=True)
        return

    if dim_mode == "custom":
        session.state = "waiting_dims_input"
        await callback.message.edit_text(
            "<b>Enter Custom Dimensions</b>\n\n"
            "Send exact dimensions (e.g. <code>800x600</code>) or maximum bounds (e.g. <code>max 1200x1200</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=build_back_keyboard(f"comp:menu_adv:{session_id}"),
        )
        await callback.answer()
        return

    session.dimension_mode = dim_mode
    session.exact_width = 0
    session.exact_height = 0
    session.max_width = 0
    session.max_height = 0
    session.scale_percent = 1.0 if dim_mode in ("auto", "100") else (int(dim_mode) / 100.0)

    text = _format_advanced_text(session)
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_advanced_settings_keyboard(session))
    await callback.answer("Dimensions updated")


@router.callback_query(F.data.startswith("adv:apply:"))
async def cb_adv_apply(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    from app.bot.handlers.compress import format_bytes, IMAGE_CARD_TEMPLATE
    w, h = session.input_dimensions
    card_text = IMAGE_CARD_TEMPLATE.format(
        fmt=session.input_format,
        size=format_bytes(session.input_file_size),
        dimensions=f"{w}×{h}",
        suggestion="",
    )
    await callback.message.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=build_image_options_keyboard(session_id))
    await callback.answer("Settings applied!")


@router.callback_query(F.data.startswith("adv:meta:"))
async def cb_adv_meta(callback: CallbackQuery, sessions: SessionStore) -> None:
    parts = callback.data.split(":")
    meta_mode = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired.", show_alert=True)
        return

    session.strip_metadata = (meta_mode == "strip")
    text = _format_advanced_text(session)
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_advanced_settings_keyboard(session))
    await callback.answer("Metadata preference updated")


# ==============================================================================
# 1-TAP RETRY HANDLERS
# ==============================================================================

@router.callback_query(F.data.startswith("retry:smaller:"))
async def cb_retry_smaller(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired. Please send image again.", show_alert=True)
        return

    out_fmt = session.selected_format or session.input_format
    out_ext = FORMAT_EXTENSIONS.get(out_fmt, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    if session.last_mode == "target" and session.last_target_kb:
        new_target = max(10, int(session.last_target_kb * 0.70))
        session.last_target_kb = new_target
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            target_bytes=new_target * 1024,
            output_format=session.selected_format,
            allow_resize=True,
            strip_metadata=session.strip_metadata,
        )
    else:
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            preset=Preset.SMALLEST,
            output_format=session.selected_format,
            allow_resize=True,
            strip_metadata=session.strip_metadata,
        )

    await callback.answer("Optimizing for smaller size...")
    await _execute_compression_job(callback, session, sessions, req, config)


@router.callback_query(F.data.startswith("retry:better:"))
async def cb_retry_better(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired. Please send image again.", show_alert=True)
        return

    out_fmt = session.selected_format or session.input_format
    out_ext = FORMAT_EXTENSIONS.get(out_fmt, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    if session.last_mode == "target" and session.last_target_kb:
        new_target = int(session.last_target_kb * 1.35)
        session.last_target_kb = new_target
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            target_bytes=new_target * 1024,
            output_format=session.selected_format,
            allow_resize=False,
            strip_metadata=session.strip_metadata,
        )
    else:
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            preset=Preset.BEST_QUALITY,
            output_format=session.selected_format,
            allow_resize=False,
            strip_metadata=session.strip_metadata,
        )

    await callback.answer("Optimizing for higher quality...")
    await _execute_compression_job(callback, session, sessions, req, config)


@router.callback_query(F.data.startswith("retry:settings:"))
async def cb_retry_settings(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.answer("Session expired. Please send image again.", show_alert=True)
        return

    text = _format_advanced_text(session)
    await callback.message.answer(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_advanced_settings_keyboard(session),
    )
    await callback.answer()
