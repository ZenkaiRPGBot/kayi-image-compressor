"""
app/bot/handlers/start.py

Handles /start command and /start help deep-link.
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, InputFile

from app.bot.keyboards.menus import build_start_keyboard
from app.bot.messages.texts import WELCOME_CAPTION, WELCOME_TEXT
from app.bot.middlewares.fsub import get_and_clear_pending_start_param

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, config: "Config") -> None:  # type: ignore[name-defined]
    """
    Handle /start [param].

    Deep-link: /start help → show help center.
    Normal: show welcome screen.
    """
    param = ""
    if command.args:
        param = command.args.strip().lower()

    # Also check pending param (set by fsub middleware)
    if not param:
        param = get_and_clear_pending_start_param(message.from_user.id)

    if param == "help":
        from app.bot.handlers.help import show_help_main
        await show_help_main(message, config)
        return

    keyboard = build_start_keyboard(channel_url=config.fsub_channel_url)

    if config.welcome_video_file_id:
        try:
            await message.answer_video(
                video=config.welcome_video_file_id,
                caption=WELCOME_CAPTION,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.warning("Failed to send welcome video (file_id=%s): %s", config.welcome_video_file_id, e)

    # Fallback: text message
    await message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=keyboard)
