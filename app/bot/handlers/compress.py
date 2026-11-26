"""
app/bot/handlers/compress.py

Handles image uploads (photos and documents), input validation,
smart image card presentation, and custom size text inputs.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from aiogram import Router, F, Bot
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from app.bot.keyboards.menus import build_image_options_keyboard, build_result_keyboard
from app.bot.messages.texts import (
    IMAGE_CARD_TEMPLATE,
    PROCESSING_TEXT,
    RESULT_CAPTION_TEMPLATE,
    RESULT_ALREADY_OPTIMAL,
    FORM_VALIDATION_FAILED,
    QUEUE_BUSY_TEXT,
    SESSION_EXPIRED_TEXT,
)
from app.compression.engine import run_compression_isolated, CompressionResult
from app.compression.formats import FORMAT_EXTENSIONS
from app.compression.presets import CompressionRequest, Preset
from app.compression.validation import validate_image_file
from app.services.cleanup import make_temp_path, cleanup_session_files
from app.services.sessions import SessionStore, UserSession

logger = logging.getLogger(__name__)
router = Router(name="compress")


def format_bytes(b: int) -> str:
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.2f} MB"
    return f"{b / 1024:.1f} KB"


async def deliver_compression_result(
    message: Message,
    session: UserSession,
    result: CompressionResult,
    config: Any,
) -> None:
    """Builds and delivers the final result card with 1-tap retry buttons."""
    stats = result.stats
    if not stats:
        await message.answer("❌ Compression failed. No output generated.", parse_mode=ParseMode.HTML)
        return

    # Target line
    target_line = ""
    if stats.target_bytes:
        target_kb = stats.target_bytes // 1024
        if stats.target_met:
            target_line = f"• <b>Target:</b> <code>{target_kb} KB (Met ✓)</code>\n"
        else:
            actual_kb = round(stats.output_bytes / 1024)
            target_line = f"• <b>Target:</b> <code>{target_kb} KB (Closest: {actual_kb} KB)</code>\n"

    # Background disclosure
    bg_line = f"• <b>Background:</b> <i>{result.background_treatment}</i>\n" if result.background_treatment else ""

    # Suggestion line
    sugg_line = f"\n{result.suggestion}\n" if result.suggestion else ""

    caption = RESULT_CAPTION_TEMPLATE.format(
        original_size=stats.original_size_str,
        output_size=stats.output_size_str,
        saved=stats.saved_str,
        reduction=stats.reduction_percent,
        fmt=stats.output_format,
        dimensions=stats.dimensions_str,
        target_line=target_line,
        background_line=bg_line,
        suggestion_line=sugg_line,
    )

    if result.form_validation_errors:
        err_text = "\n".join(f"• {e}" for e in result.form_validation_errors)
        caption += f"\n" + FORM_VALIDATION_FAILED.format(errors=err_text)

    # Keyboard with 1-tap retries (passes success flag so failed targets don't show green success)
    markup = build_result_keyboard(session.session_id, success=result.success)

    # Deliver document
    input_file = FSInputFile(result.output_path, filename=os.path.basename(result.output_path))
    await message.answer_document(
        document=input_file,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


async def _handle_image_upload(
    message: Message,
    file_id: str,
    file_size: int,
    config: Any,
    sessions: SessionStore,
    rate_limiter: Any,
) -> None:
    user = message.from_user
    if not user:
        return

    # 1. Rate limiter check before downloading
    allowed, reason = rate_limiter.check(user.id)
    if not allowed:
        await message.answer(f"⚠️ <b>Rate Limit</b>\n\n{reason}", parse_mode=ParseMode.HTML)
        return

    # 2. Max size check on Telegram file metadata before downloading
    if file_size > config.max_upload_bytes:
        limit_mb = config.max_upload_bytes / (1024 * 1024)
        await message.answer(
            f"❌ <b>File Too Large</b>\n\n"
            f"Image is {format_bytes(file_size)}. Maximum upload allowed is {limit_mb:.0f} MB.",
            parse_mode=ParseMode.HTML,
        )
        return

    status_msg = await message.answer("⚡ <i>Analysing image...</i>", parse_mode=ParseMode.HTML)

    # 3. Download to unique temp file
    temp_path = make_temp_path("bin", config.max_storage_budget_bytes)
    try:
        tg_file = await message.bot.get_file(file_id)
        if not tg_file.file_path:
            await status_msg.edit_text("❌ Could not retrieve file from Telegram.", parse_mode=ParseMode.HTML)
            cleanup_session_files(temp_path)
            return
        await message.bot.download_file(tg_file.file_path, destination=temp_path)
    except Exception as e:
        logger.error("Download failed for user %s: %s", user.id, e)
        await status_msg.edit_text(f"❌ Failed to download file: {e}", parse_mode=ParseMode.HTML)
        cleanup_session_files(temp_path)
        return

    # 4. Strict validation (magic bytes, pixel limit, decompression bombs, animated check)
    v = await asyncio.to_thread(
        validate_image_file, temp_path, config.max_upload_bytes, config.max_image_pixels
    )
    if not v.ok:
        cleanup_session_files(temp_path)
        await status_msg.edit_text(f"❌ <b>Image Rejected</b>\n\n{v.error_message}", parse_mode=ParseMode.HTML)
        return

    rate_limiter.record(user.id)

    # 5. Initialize session
    session = sessions.create(user.id)
    session.input_file_id = file_id
    session.input_file_path = temp_path
    session.input_file_size = v.file_size
    session.input_format = v.format
    session.input_dimensions = v.dimensions
    session.state = "waiting_choice"

    # Smart suggestion
    suggestion = ""
    w, h = v.dimensions
    if w > 2500 or h > 2500:
        suggestion = "💡 <i>Tip: Large resolution detected. Resizing will achieve massive size reduction.</i>\n"
    elif v.file_size < 40 * 1024:
        suggestion = "💡 <i>Notice: Image is already under 40 KB.</i>\n"

    card_text = IMAGE_CARD_TEMPLATE.format(
        fmt=v.format,
        size=format_bytes(v.file_size),
        dimensions=f"{w}×{h}",
        suggestion=suggestion,
    )
    markup = build_image_options_keyboard(session.session_id)

    await status_msg.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=markup)


@router.message(Command("compress"))
async def cmd_compress(message: Message) -> None:
    await message.answer(
        "<b>Compress an Image</b>\n\n"
        "Send me any JPEG, PNG, or WebP photo or file to begin.",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.photo)
async def handle_photo(
    message: Message,
    config: Any,
    sessions: SessionStore,
    rate_limiter: Any,
) -> None:
    photo = message.photo[-1]
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
    config: Any,
    sessions: SessionStore,
    rate_limiter: Any,
) -> None:
    doc = message.document
    mime = (doc.mime_type or "").lower()
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        await message.answer(
            "<b>Unsupported Format</b>\n\nPlease send a JPEG, PNG, or WebP image file.",
            parse_mode=ParseMode.HTML,
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
async def handle_custom_text(
    message: Message,
    sessions: SessionStore,
    config: Any,
) -> None:
    """Parses custom sizes in KB/MB or dimensions in WxH."""
    user = message.from_user
    if not user:
        return
    session = sessions.get_by_user(user.id)
    if not session:
        return

    text = message.text.strip().lower()

    # --- Mode: Custom Target Size ---
    if session.state == "waiting_target_input":
        # Check for MB or KB
        kb_val = 0
        mb_match = re.search(r"(\d+(?:\.\d+)?)\s*mb", text)
        kb_match = re.search(r"(\d+(?:\.\d+)?)\s*kb", text)
        num_match = re.search(r"^(\d+(?:\.\d+)?)$", text)

        if mb_match:
            kb_val = int(float(mb_match.group(1)) * 1024)
        elif kb_match:
            kb_val = int(float(kb_match.group(1)))
        elif num_match:
            kb_val = int(float(num_match.group(1)))

        if kb_val <= 0 or kb_val > 50 * 1024:
            await message.answer("⚠️ Please enter a valid size between 10 KB and 50 MB (e.g. <code>150 KB</code> or <code>1.5 MB</code>).", parse_mode=ParseMode.HTML)
            return

        session.last_mode = "target"
        session.last_target_kb = kb_val
        session.state = "processing"

        status_msg = await message.answer(PROCESSING_TEXT, parse_mode=ParseMode.HTML)

        out_fmt = session.selected_format or session.input_format
        out_ext = FORMAT_EXTENSIONS.get(out_fmt, "jpg")
        output_path = make_temp_path(out_ext, config.max_storage_budget_bytes)

        allow_downscale = (session.dimension_mode == "auto")

        req = CompressionRequest(
            input_path=session.input_file_path,
            output_path=output_path,
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

        try:
            res = await run_compression_isolated(req, timeout_seconds=config.processing_timeout_seconds)
            session.output_file_path = res.output_path
            session.state = "done"
            await status_msg.delete()
            await deliver_compression_result(message, session, res, config)
        except asyncio.TimeoutError:
            session.state = "error"
            await status_msg.edit_text("⏱ Processing timed out. Worker process was terminated.", parse_mode=ParseMode.HTML)
        except Exception as e:
            session.state = "error"
            await status_msg.edit_text(f"❌ Processing error: {e}", parse_mode=ParseMode.HTML)

    # --- Mode: Custom Dimensions (e.g. 800x600 or max 1200x1200) ---
    max_match = re.search(r"^max\s+(\d{2,5})\s*[x×*]\s*(\d{2,5})$", text)
    dims_match = re.search(r"^(\d{2,5})\s*[x×*]\s*(\d{2,5})$", text)
    if max_match or dims_match:
        session.dimension_mode = "custom"
        session.scale_percent = 1.0
        session.state = "waiting_choice"
        if max_match:
            mw, mh = int(max_match.group(1)), int(max_match.group(2))
            session.max_width = mw
            session.max_height = mh
            session.exact_width = 0
            session.exact_height = 0
        else:
            dw, dh = int(dims_match.group(1)), int(dims_match.group(2))
            session.exact_width = dw
            session.exact_height = dh
            session.max_width = 0
            session.max_height = 0

        from app.bot.handlers.callbacks import _format_advanced_text
        from app.bot.keyboards.menus import build_advanced_settings_keyboard
        await message.answer(
            text=_format_advanced_text(session),
            parse_mode=ParseMode.HTML,
            reply_markup=build_advanced_settings_keyboard(session),
        )
    elif session.state == "waiting_dims_input":
        from app.bot.keyboards.menus import build_back_keyboard
        await message.answer(
            "⚠️ Invalid format. Send exact dimensions (e.g. <code>800x600</code>) or maximum bounds (e.g. <code>max 1200x1200</code>).",
            parse_mode=ParseMode.HTML,
            reply_markup=build_back_keyboard(f"comp:menu_adv:{session.session_id}"),
        )
