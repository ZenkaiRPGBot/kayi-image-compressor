"""
app/bot/handlers/compress.py

Handles image upload flow:
  - /compress command
  - Photo messages
  - Document messages (image files)
  - Custom target size text input
"""
from __future__ import annotations

import logging
import os
import asyncio
import tempfile
import uuid
from concurrent.futures import ProcessPoolExecutor

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.menus import build_image_options_keyboard
from app.bot.messages.texts import (
    IMAGE_RECEIVED,
    PROCESSING,
    TARGET_PROMPT,
    TARGET_INVALID,
    SESSION_EXPIRED,
    COMPRESSION_FAILED,
    TIMEOUT_ERROR,
    RESULT_SUCCESS,
    RESULT_GREW,
    TARGET_MET,
    TARGET_NOT_MET,
    ANOTHER_IMAGE,
)
from app.compression.engine import compress_image_sync, CompressionResult
from app.compression.formats import FORMAT_EXTENSIONS
from app.compression.presets import CompressionRequest, Preset
from app.compression.validation import validate_image_file
from app.services.cleanup import cleanup_session_files, make_temp_path
from app.services.sessions import SessionStore

logger = logging.getLogger(__name__)
router = Router(name="compress")

# Global process pool — 1 worker, shared across all requests
_pool: ProcessPoolExecutor | None = None


def get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=1)
    return _pool


def _fmt_size(b: int) -> str:
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.2f} MB"
    return f"{b / 1024:.1f} KB"


def _fmt_dimensions(w: int, h: int) -> str:
    return f"{w}×{h}"


async def _download_file(bot: Bot, file_id: str, dest_path: str) -> None:
    """Download a Telegram file to dest_path."""
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, destination=dest_path)


async def _handle_image_upload(
    message: Message,
    file_id: str,
    file_size: int,
    config: "Config",  # type: ignore[name-defined]
    sessions: SessionStore,
    rate_limiter: "RateLimiter",  # type: ignore[name-defined]
) -> None:
    """
    Common handler for photo and document image uploads.
    Downloads, validates, creates session, shows options.
    """
    user = message.from_user

    # Rate limit — record usage
    rate_limiter.record(user.id)

    # Check file size from Telegram metadata
    if file_size > config.max_upload_bytes:
        limit_mb = config.max_upload_bytes / (1024 * 1024)
        await message.answer(
            f"❌ File too large ({_fmt_size(file_size)}). Maximum is {limit_mb:.0f} MB.",
            parse_mode="HTML",
        )
        return

    # Send "downloading…" indicator
    status_msg = await message.answer("⏳ Analysing your image…", parse_mode="HTML")

    # Download
    ext = "bin"
    input_path = make_temp_path(ext)
    try:
        await _download_file(message.bot, file_id, input_path)
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to download image: {e}", parse_mode="HTML")
        return

    # Validate
    validation = validate_image_file(input_path, config.max_upload_bytes, config.max_image_pixels)
    if not validation.ok:
        cleanup_session_files(input_path)
        await status_msg.edit_text(f"❌ {validation.error_message}", parse_mode="HTML")
        return

    # Create session
    session = sessions.create(user.id)
    session.input_file_id = file_id
    session.input_file_path = input_path
    session.input_file_size = validation.file_size
    session.input_format = validation.format
    session.input_dimensions = validation.dimensions
    session.state = "waiting_choice"

    w, h = validation.dimensions
    text = IMAGE_RECEIVED.format(
        fmt=validation.format,
        size=_fmt_size(validation.file_size),
        dimensions=_fmt_dimensions(w, h),
    )
    keyboard = build_image_options_keyboard(session.session_id)
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("compress"))
async def cmd_compress(message: Message) -> None:
    await message.answer("Send me an image (JPEG, PNG, or WebP) and I'll compress it for you.", parse_mode="HTML")


@router.message(F.photo)
async def handle_photo(
    message: Message,
    config: "Config",  # type: ignore[name-defined]
    sessions: SessionStore,
    rate_limiter: "RateLimiter",  # type: ignore[name-defined]
) -> None:
    photo = message.photo[-1]  # Largest available
    await _handle_image_upload(
        message=message,
        file_id=photo.file_id,
        file_size=photo.file_size or 0,
        config=config,
        sessions=sessions,
        rate_limiter=rate_limiter,
    )


@router.message(F.document)
async def handle_document(
    message: Message,
    config: "Config",  # type: ignore[name-defined]
    sessions: SessionStore,
    rate_limiter: "RateLimiter",  # type: ignore[name-defined]
) -> None:
    doc = message.document
    mime = doc.mime_type or ""
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        await message.answer(
            "Please send a JPEG, PNG, or WebP image file.",
            parse_mode="HTML",
        )
        return
    await _handle_image_upload(
        message=message,
        file_id=doc.file_id,
        file_size=doc.file_size or 0,
        config=config,
        sessions=sessions,
        rate_limiter=rate_limiter,
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_input(
    message: Message,
    sessions: SessionStore,
) -> None:
    """
    Handles free-text input — used for custom target size entry.
    """
    user = message.from_user
    session = sessions.get_by_user(user.id)
    if session is None or session.state != "waiting_target_input":
        return  # Not in an active target-size flow; ignore

    text = message.text.strip().replace("kb", "").replace("KB", "").replace("mb", "").strip()
    try:
        kb = int(float(text))
        if kb <= 0:
            raise ValueError
    except ValueError:
        await message.answer(TARGET_INVALID, parse_mode="HTML")
        return

    session.pending_target_kb = kb
    session.state = "waiting_choice"

    # Trigger compression immediately
    await _run_compression_target(message, session, kb * 1024, sessions)


async def _run_compression_target(
    message: Message,
    session: "UserSession",  # type: ignore[name-defined]
    target_bytes: int,
    sessions: SessionStore,
) -> None:
    """Run target-size compression and deliver result."""
    from app.bot.keyboards.menus import build_result_keyboard

    status_msg = await message.answer(PROCESSING, parse_mode="HTML")
    session.state = "processing"

    input_path = session.input_file_path
    output_ext = FORMAT_EXTENSIONS.get(session.input_format, "jpg")
    output_path = make_temp_path(output_ext)

    request = CompressionRequest(
        input_path=input_path,
        output_path=output_path,
        target_bytes=target_bytes,
        output_format=session.input_format,
        allow_resize=True,
        strip_metadata=True,
    )

    loop = asyncio.get_event_loop()
    try:
        result: CompressionResult = await asyncio.wait_for(
            loop.run_in_executor(get_pool(), compress_image_sync, request),
            timeout=25.0,
        )
    except asyncio.TimeoutError:
        session.state = "error"
        await status_msg.edit_text(TIMEOUT_ERROR, parse_mode="HTML")
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)
        return
    except Exception as e:
        session.state = "error"
        await status_msg.edit_text(COMPRESSION_FAILED.format(error=str(e)), parse_mode="HTML")
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)
        return

    if not result.success or not result.stats:
        await status_msg.edit_text(COMPRESSION_FAILED.format(error=result.error), parse_mode="HTML")
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
        if result.target_result:
            if result.target_result.success:
                caption += TARGET_MET.format(target_kb=target_bytes // 1024)
            else:
                caption += TARGET_NOT_MET.format(
                    actual_kb=round(stats.output_bytes / 1024),
                    reason=result.target_result.reason,
                )

    keyboard = build_result_keyboard(session.session_id)
    try:
        await status_msg.delete()
        await message.answer_document(
            document=open(result.output_path, "rb"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        await message.answer(f"❌ Failed to send result: {e}", parse_mode="HTML")
    finally:
        cleanup_session_files(input_path, output_path)
        sessions.delete(session.session_id)
