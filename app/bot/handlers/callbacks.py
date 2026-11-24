"""
app/bot/handlers/callbacks.py

All inline keyboard callback handlers for Kayi Image Compressor.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from app.bot.keyboards.menus import (
    build_image_options_keyboard,
    build_quality_presets_keyboard,
    build_result_keyboard,
    build_target_size_keyboard,
)
from app.bot.messages.texts import (
    COMPRESSION_FAILED,
    FSUB_NOT_JOINED,
    PROCESSING,
    QUEUE_FULL,
    RESULT_GREW,
    RESULT_SUCCESS,
    SESSION_EXPIRED,
    TARGET_MET,
    TARGET_NOT_MET,
    TARGET_PROMPT,
    CANCEL_OK,
    ANOTHER_IMAGE,
)
from app.compression.engine import compress_image_sync, CompressionResult
from app.compression.formats import FORMAT_EXTENSIONS
from app.compression.presets import CompressionRequest, Preset
from app.services.cleanup import cleanup_session_files, make_temp_path
from app.services.sessions import SessionStore

logger = logging.getLogger(__name__)
router = Router(name="callbacks")

# Global pool reference — set by main.py
_pool = None


def set_pool(pool) -> None:
    global _pool
    _pool = pool


def _get_pool():
    global _pool
    if _pool is None:
        from concurrent.futures import ProcessPoolExecutor
        _pool = ProcessPoolExecutor(max_workers=1)
    return _pool


def _fmt_size(b: int) -> str:
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.2f} MB"
    return f"{b / 1024:.1f} KB"


def _fmt_dimensions(w: int, h: int) -> str:
    return f"{w}×{h}"


async def _run_preset_compression(
    callback: CallbackQuery,
    session,
    sessions: SessionStore,
    preset: Preset,
    config,
) -> None:
    """Execute preset-based compression and deliver the result."""
    session.state = "processing"
    input_path = session.input_file_path
    output_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    output_path = make_temp_path(output_ext)

    request = CompressionRequest(
        input_path=input_path,
        output_path=output_path,
        preset=preset,
        output_format=session.input_format,
        strip_metadata=True,
    )

    status_msg = await callback.message.edit_text(PROCESSING, parse_mode="HTML")
    loop = asyncio.get_event_loop()

    try:
        result: CompressionResult = await asyncio.wait_for(
            loop.run_in_executor(_get_pool(), compress_image_sync, request),
            timeout=config.processing_timeout_seconds,
        )
    except asyncio.TimeoutError:
        session.state = "error"
        await callback.message.edit_text(
            "⏱ Processing timed out. Please try again with a smaller image.",
            parse_mode="HTML",
        )
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)
        return
    except Exception as e:
        session.state = "error"
        await callback.message.edit_text(COMPRESSION_FAILED.format(error=str(e)), parse_mode="HTML")
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)
        return

    if not result.success or not result.stats:
        await callback.message.edit_text(COMPRESSION_FAILED.format(error=result.error), parse_mode="HTML")
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)
        return

    stats = result.stats
    w, h = stats.output_dimensions

    if stats.grew:
        caption = RESULT_GREW.format(
            output_size=stats.output_size_str,
            original_size=stats.original_size_str,
        )
    else:
        caption = RESULT_SUCCESS.format(
            original_size=stats.original_size_str,
            output_size=stats.output_size_str,
            saved=stats.saved_str,
            reduction=stats.reduction_percent,
            fmt=stats.output_format,
            dimensions=_fmt_dimensions(w, h),
        )

    keyboard = build_result_keyboard(session.session_id, config.fsub_channel_url)
    try:
        await callback.message.delete()
        await callback.message.answer_document(
            document=open(result.output_path, "rb"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        await callback.message.answer(f"❌ Failed to send: {e}", parse_mode="HTML")
    finally:
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)


# ─── FSub ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "fsub:check")
async def cb_fsub_check(callback: CallbackQuery, config) -> None:
    from app.bot.middlewares.fsub import check_channel_membership, get_and_clear_pending_start_param
    is_member, _ = await check_channel_membership(callback.bot, callback.from_user.id, config.fsub_channel)
    if is_member:
        from app.bot.keyboards.menus import build_start_keyboard
        from app.bot.messages.texts import WELCOME_TEXT
        keyboard = build_start_keyboard(channel_url=config.fsub_channel_url)
        await callback.message.edit_text(WELCOME_TEXT, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer("✅ Welcome! You're now verified.")
    else:
        await callback.answer(FSUB_NOT_JOINED, show_alert=True)


# ─── Compress: start ───────────────────────────────────────────────────────

@router.callback_query(F.data == "compress:start")
async def cb_compress_start(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Send me an image (JPEG, PNG, or WebP) to compress it.",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Compress: auto ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("compress:auto:"))
async def cb_compress_auto(callback: CallbackQuery, sessions: SessionStore, config) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if session is None or session.user_id != callback.from_user.id:
        await callback.message.edit_text(SESSION_EXPIRED, parse_mode="HTML")
        await callback.answer()
        return
    await callback.answer()
    await _run_preset_compression(callback, session, sessions, Preset.BALANCED, config)


# ─── Compress: presets menu ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("compress:presets:"))
async def cb_compress_presets_menu(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if session is None or session.user_id != callback.from_user.id:
        await callback.message.edit_text(SESSION_EXPIRED, parse_mode="HTML")
        await callback.answer()
        return
    keyboard = build_quality_presets_keyboard(session_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


# ─── Compress: specific preset ────────────────────────────────────────────

@router.callback_query(F.data.startswith("compress:preset:"))
async def cb_compress_preset(callback: CallbackQuery, sessions: SessionStore, config) -> None:
    parts = callback.data.split(":")
    # compress:preset:<preset_name>:<session_id>
    preset_name = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if session is None or session.user_id != callback.from_user.id:
        await callback.message.edit_text(SESSION_EXPIRED, parse_mode="HTML")
        await callback.answer()
        return

    try:
        preset = Preset(preset_name)
    except ValueError:
        await callback.answer("Unknown preset.", show_alert=True)
        return

    await callback.answer()
    await _run_preset_compression(callback, session, sessions, preset, config)


# ─── Compress: target menu ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("compress:target_menu:"))
async def cb_target_menu(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if session is None or session.user_id != callback.from_user.id:
        await callback.message.edit_text(SESSION_EXPIRED, parse_mode="HTML")
        await callback.answer()
        return
    keyboard = build_target_size_keyboard(session_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


# ─── Compress: specific target size ───────────────────────────────────────

@router.callback_query(F.data.startswith("compress:target:"))
async def cb_target_size(callback: CallbackQuery, sessions: SessionStore, config) -> None:
    parts = callback.data.split(":")
    # compress:target:<kb_or_custom>:<session_id>
    target_str = parts[2]
    session_id = parts[3]

    session = sessions.get(session_id)
    if session is None or session.user_id != callback.from_user.id:
        await callback.message.edit_text(SESSION_EXPIRED, parse_mode="HTML")
        await callback.answer()
        return

    if target_str == "custom":
        # Prompt for custom input
        session.state = "waiting_target_input"
        input_size = _fmt_size(session.input_file_size)
        await callback.message.edit_text(
            TARGET_PROMPT.format(size=input_size),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    try:
        target_kb = int(target_str)
        target_bytes = target_kb * 1024
    except ValueError:
        await callback.answer("Invalid target size.", show_alert=True)
        return

    await callback.answer()

    # Run target-size compression
    from app.bot.handlers.compress import _run_compression_target
    await _run_compression_target(callback.message, session, target_bytes, sessions)


# ─── Compress: back to options ────────────────────────────────────────────

@router.callback_query(F.data.startswith("compress:back_options:"))
async def cb_back_to_options(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if session is None:
        await callback.message.edit_text(SESSION_EXPIRED, parse_mode="HTML")
        await callback.answer()
        return
    keyboard = build_image_options_keyboard(session_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


# ─── Compress: cancel ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("compress:cancel:"))
async def cb_cancel(callback: CallbackQuery, sessions: SessionStore) -> None:
    session_id = callback.data.split(":", 2)[2]
    session = sessions.get(session_id)
    if session:
        cleanup_session_files(session.input_file_path, session.output_file_path)
        sessions.delete(session_id)
    await callback.message.edit_text(CANCEL_OK, parse_mode="HTML")
    await callback.answer()


# ─── Compress: another ────────────────────────────────────────────────────

@router.callback_query(F.data == "compress:another")
async def cb_another(callback: CallbackQuery) -> None:
    await callback.message.edit_caption(
        caption=ANOTHER_IMAGE,
        parse_mode="HTML",
    ) if callback.message.caption else await callback.message.edit_text(ANOTHER_IMAGE, parse_mode="HTML")
    await callback.answer()


# ─── Settings ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:open")
async def cb_settings(callback: CallbackQuery) -> None:
    # Settings are session-local and ephemeral — no persistent config to show
    await callback.answer(
        "Settings are applied per compression session. Choose a preset or target when compressing.",
        show_alert=True,
    )
