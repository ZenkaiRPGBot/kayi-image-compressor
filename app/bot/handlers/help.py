"""
app/bot/handlers/help.py

Handles /help and /privacy commands.
Matches the official, clean typographic standard of the Kayi Bots ecosystem.
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.bot.keyboards.menus import build_help_keyboard
from app.bot.messages.texts import HELP_TEXT, PRIVACY_TEXT

logger = logging.getLogger(__name__)
router = Router(name="help")


async def show_help_main(event: Message | CallbackQuery, config: Any) -> None:
    keyboard = build_help_keyboard(developer_url="https://t.me/qouba")
    if isinstance(event, Message):
        await event.answer(
            text=HELP_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    elif isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(
                text=HELP_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            await event.message.answer(
                text=HELP_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        await event.answer()


@router.message(Command("help"))
async def cmd_help(message: Message, config: Any) -> None:
    await show_help_main(message, config)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    keyboard = build_help_keyboard(developer_url="https://t.me/qouba")
    await message.answer(
        text=PRIVACY_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
