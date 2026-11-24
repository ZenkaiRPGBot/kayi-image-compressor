"""
app/bot/handlers/help.py

Handles /help and /privacy commands and their callback navigation.
"""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.bot.keyboards.menus import (
    build_help_keyboard,
    build_help_privacy_keyboard,
    build_start_keyboard,
)
from app.bot.messages.texts import HELP_MAIN, HELP_PRIVACY

logger = logging.getLogger(__name__)
router = Router(name="help")


async def show_help_main(event: "Message | CallbackQuery", config: "Config") -> None:  # type: ignore[name-defined]
    keyboard = build_help_keyboard()
    if isinstance(event, Message):
        await event.answer(HELP_MAIN, parse_mode="HTML", reply_markup=keyboard)
    elif isinstance(event, CallbackQuery):
        await event.message.edit_text(HELP_MAIN, parse_mode="HTML", reply_markup=keyboard)
        await event.answer()


@router.message(Command("help"))
async def cmd_help(message: Message, config: "Config") -> None:  # type: ignore[name-defined]
    await show_help_main(message, config)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    keyboard = build_help_privacy_keyboard()
    await message.answer(HELP_PRIVACY, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "help:main")
async def cb_help_main(callback: CallbackQuery, config: "Config") -> None:  # type: ignore[name-defined]
    await show_help_main(callback, config)


@router.callback_query(F.data == "help:privacy")
async def cb_help_privacy(callback: CallbackQuery) -> None:
    keyboard = build_help_privacy_keyboard()
    await callback.message.edit_text(HELP_PRIVACY, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "help:back")
async def cb_help_back(callback: CallbackQuery, config: "Config") -> None:  # type: ignore[name-defined]
    """Return to the start screen."""
    from app.bot.messages.texts import WELCOME_TEXT
    keyboard = build_start_keyboard(channel_url=config.fsub_channel_url)
    await callback.message.edit_text(WELCOME_TEXT, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()
