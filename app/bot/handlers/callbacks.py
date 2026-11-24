"""
app/bot/handlers/callbacks.py

All callback query handlers for Kayi Image Compressor.
Handles FSub verification, preset selection, target-size menus,
form upload mode, advanced controls, and 1-tap retries.
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
    build_image_options_keyboard,
    build_target_size_keyboard,
    build_quality_presets_keyboard,
    build_specialized_presets_keyboard,
    build_form_upload_keyboard,
    build_advanced_controls_keyboard,
    build_result_keyboard,
)
from app.bot.messages.texts import (
    PROCESSING_TEXT,
    SESSION_EXPIRED_TEXT,
    QUEUE_BUSY_TEXT,
    HELP_TEXT,
    WELCOME_TEXT,
)
from app.bot.middlewares.fsub import (
    check_channel_membership,
    get_and_clear_pending_start_param,
)
from app.compression.engine import run_compression_isolated, CompressionResult
from app.compression.formats import FORMAT_EXTENSIONS
from app.compression.presets import CompressionRequest, Preset
from app.services.cleanup import make_temp_path, cleanup_session_files
from app.services.sessions import SessionStore, UserSession

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


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

        # Deliver result
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
# NAVIGATION & MENUS
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

    await callback.message.edit_reply_markup(reply_markup=build_image_options_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("comp:cancel:"))
async def cb_cancel(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    sessions.delete(session_id)
    await callback.message.edit_text("✦ <i>Compression cancelled. Send another image anytime.</i>", parse_mode=ParseMode.HTML)
    await callback.answer()


# ==============================================================================
# AUTO OPTIMIZE
# ==============================================================================

@router.callback_query(F.data.startswith("comp:auto:"))
async def cb_auto(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    session.last_mode = "preset"
    session.last_preset = Preset.BALANCED.value
    session.last_quality = 75

    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        preset=Preset.BALANCED,
        output_format=session.input_format,
        strip_metadata=True,
    )
    await callback.answer()
    await _execute_compression_job(callback, session, sessions, req, config)


# ==============================================================================
# TARGET SIZE MENUS & ACTIONS
# ==============================================================================

@router.callback_query(F.data.startswith("comp:menu_target:"))
async def cb_menu_target(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=build_target_size_keyboard(session_id))
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
            "Send the desired file size in KB or MB (e.g. <code>50 KB</code> or <code>1.5 MB</code>):",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    kb_val = int(kb_str)
    session.last_mode = "target"
    session.last_target_kb = kb_val

    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        target_bytes=kb_val * 1024,
        output_format=session.input_format,
        allow_resize=True,
        strip_metadata=True,
    )
    await callback.answer()
    await _execute_compression_job(callback, session, sessions, req, config)


# ==============================================================================
# QUALITY & SPECIALIZED PRESETS
# ==============================================================================

@router.callback_query(F.data.startswith("comp:menu_presets:"))
async def cb_menu_presets(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=build_quality_presets_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("comp:menu_spec:"))
async def cb_menu_spec(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=build_specialized_presets_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("comp:preset:"))
async def cb_preset_select(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    parts = callback.data.split(":")
    preset_name = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    preset = Preset(preset_name)
    session.last_mode = "preset"
    session.last_preset = preset_name

    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        preset=preset,
        output_format=session.input_format,
        strip_metadata=True,
    )
    await callback.answer()
    await _execute_compression_job(callback, session, sessions, req, config)


# ==============================================================================
# FORM UPLOAD MODE (FLAGSHIP GUIDED WORKFLOW)
# ==============================================================================

@router.callback_query(F.data.startswith("comp:menu_form:"))
async def cb_menu_form(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    text = (
        "<b>📋 Form Upload Mode — Step 1/3</b>\n\n"
        "Select maximum required file size allowed by the portal:"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_form_upload_keyboard(session_id, stage="size"))
    await callback.answer()


@router.callback_query(F.data.startswith("form:size:"))
async def cb_form_size(callback: CallbackQuery, sessions: SessionStore) -> None:
    parts = callback.data.split(":")
    size_str = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    if size_str == "custom":
        session.state = "waiting_form_size_input"
        await callback.message.edit_text("<b>Enter Portal Max Size (KB):</b>", parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    session.form_max_kb = int(size_str)
    text = (
        f"<b>📋 Form Upload Mode — Step 2/3</b>\n\n"
        f"• <b>Max Size:</b> <code>{session.form_max_kb} KB</code>\n\n"
        "Select required output format:"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_form_upload_keyboard(session_id, stage="format"))
    await callback.answer()


@router.callback_query(F.data.startswith("form:fmt:"))
async def cb_form_fmt(callback: CallbackQuery, sessions: SessionStore) -> None:
    parts = callback.data.split(":")
    fmt_str = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    session.form_format = "" if fmt_str == "KEEP" else fmt_str
    fmt_display = session.form_format or f"Keep ({session.input_format})"

    text = (
        f"<b>📋 Form Upload Mode — Step 3/3</b>\n\n"
        f"• <b>Max Size:</b> <code>{session.form_max_kb} KB</code>\n"
        f"• <b>Format:</b> <code>{fmt_display}</code>\n\n"
        "Select framing preference (never distorts or stretches):"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_form_upload_keyboard(session_id, stage="fit"))
    await callback.answer()


@router.callback_query(F.data.startswith("form:fit:"))
async def cb_form_fit(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    parts = callback.data.split(":")
    fit_choice = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    exact_w, exact_h = 0, 0
    fit_mode = "fit"

    if fit_choice == "pad_sq":
        exact_w, exact_h = 600, 600
        fit_mode = "pad"
    elif fit_choice == "crop_sq":
        exact_w, exact_h = 600, 600
        fit_mode = "crop"
    elif fit_choice == "pad_pass":
        exact_w, exact_h = 600, 800
        fit_mode = "pad"
    elif fit_choice == "crop_pass":
        exact_w, exact_h = 600, 800
        fit_mode = "crop"

    session.last_mode = "form"
    target_bytes = (session.form_max_kb or 100) * 1024
    session.last_target_kb = session.form_max_kb

    out_ext = FORMAT_EXTENSIONS.get(session.form_format or session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        target_bytes=target_bytes,
        output_format=session.form_format or session.input_format,
        exact_width=exact_w,
        exact_height=exact_h,
        fit_mode=fit_mode,
        allow_resize=True,
        is_form_mode=True,
        form_max_bytes=target_bytes,
        strip_metadata=True,
    )
    await callback.answer()
    await _execute_compression_job(callback, session, sessions, req, config)


# ==============================================================================
# ADVANCED CONTROLS
# ==============================================================================

@router.callback_query(F.data.startswith("comp:menu_adv:"))
async def cb_menu_adv(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    text = "<b>⚙️ Advanced Image Controls</b>\n\nApply custom scaling, format conversions, or EXIF preferences:"
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_advanced_controls_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("adv:scale:"))
async def cb_adv_scale(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    parts = callback.data.split(":")
    scale_int = int(parts[2])
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        preset=Preset.BALANCED,
        output_format=session.input_format,
        scale_percent=scale_int / 100.0,
        strip_metadata=True,
    )
    await callback.answer(f"Scaling to {scale_int}%...")
    await _execute_compression_job(callback, session, sessions, req, config)


@router.callback_query(F.data.startswith("adv:fmt:"))
async def cb_adv_fmt(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    parts = callback.data.split(":")
    fmt_target = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    out_ext = FORMAT_EXTENSIONS.get(fmt_target, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        preset=Preset.BALANCED,
        output_format=fmt_target,
        strip_metadata=True,
    )
    await callback.answer(f"Converting to {fmt_target}...")
    await _execute_compression_job(callback, session, sessions, req, config)


@router.callback_query(F.data.startswith("adv:meta:"))
async def cb_adv_meta(callback: CallbackQuery, sessions: SessionStore, config: Any) -> None:
    parts = callback.data.split(":")
    meta_mode = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if not session or not os.path.exists(session.input_file_path):
        await callback.message.edit_text(SESSION_EXPIRED_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    strip_meta = (meta_mode == "strip")
    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    req = CompressionRequest(
        input_path=session.input_file_path,
        output_path=out_path,
        preset=Preset.BALANCED,
        output_format=session.input_format,
        strip_metadata=strip_meta,
    )
    action_text = "Stripping metadata..." if strip_meta else "Preserving metadata..."
    await callback.answer(action_text)
    await _execute_compression_job(callback, session, sessions, req, config)


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

    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    if session.last_mode == "target" and session.last_target_kb:
        new_target = max(10, int(session.last_target_kb * 0.70))
        session.last_target_kb = new_target
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            target_bytes=new_target * 1024,
            output_format=session.input_format,
            allow_resize=True,
            strip_metadata=True,
        )
    else:
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            preset=Preset.SMALLEST,
            output_format=session.input_format,
            allow_resize=True,
            strip_metadata=True,
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

    out_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    out_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

    if session.last_mode == "target" and session.last_target_kb:
        new_target = int(session.last_target_kb * 1.35)
        session.last_target_kb = new_target
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            target_bytes=new_target * 1024,
            output_format=session.input_format,
            allow_resize=False,
            strip_metadata=True,
        )
    else:
        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=out_path,
            preset=Preset.BEST_QUALITY,
            output_format=session.input_format,
            allow_resize=False,
            strip_metadata=True,
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

    await callback.message.answer(
        "<b>Compression Settings</b>\n\nChoose new settings for your active image:",
        parse_mode=ParseMode.HTML,
        reply_markup=build_image_options_keyboard(session_id),
    )
    await callback.answer()
