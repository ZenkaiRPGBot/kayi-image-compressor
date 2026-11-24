"""
app/bot/handlers/start.py

Handles /start command, deep-linking, and cinematic welcome video delivery.
Matches the official standards of the Kayi Bots ecosystem.
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message

from app.bot.keyboards.menus import build_welcome_keyboard
from app.bot.messages.texts import WELCOME_CAPTION, WELCOME_TEXT
from app.bot.middlewares.fsub import get_and_clear_pending_start_param

logger = logging.getLogger(__name__)
router = Router(name="start")


async def send_welcome_screen(message: Message, config: Any) -> None:
    """Delivers the official welcome screen with cached video or fallback text."""
    markup = build_welcome_keyboard(
        channel_url=config.fsub_channel_url,
        developer_url="https://t.me/qouba",
    )

    if config.welcome_video_file_id:
        try:
            await message.answer_video(
                video=config.welcome_video_file_id,
                caption=WELCOME_CAPTION,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                supports_streaming=True,
            )
            return
        except Exception as e:
            logger.warning("Cinematic welcome video delivery failed (file_id=%s): %s", config.welcome_video_file_id, e)

    await message.answer(
        text=WELCOME_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, config: Any) -> None:
    """
    Handle /start [param].
    Preserves /start help deep-link across FSub checks.
    """
    param = ""
    if command.args:
        param = command.args.strip().lower()

    if not param:
        param = get_and_clear_pending_start_param(message.from_user.id) or ""

    if param == "help":
        from app.bot.handlers.help import show_help_main
        await show_help_main(message, config)
        return

    await send_welcome_screen(message, config)
