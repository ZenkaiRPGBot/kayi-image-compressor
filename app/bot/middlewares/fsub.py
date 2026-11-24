"""
app/bot/middlewares/fsub.py

Force-subscribe middleware for Kayi Image Compressor.
Identical pattern to other Kayi Bots — checks membership before handling any update.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

logger = logging.getLogger(__name__)

# In-memory store for preserving /start params across fsub check
_pending_start_params: Dict[int, str] = {}


def set_pending_start_param(user_id: int, param: str) -> None:
    if param:
        _pending_start_params[user_id] = param


def get_and_clear_pending_start_param(user_id: int) -> str:
    return _pending_start_params.pop(user_id, "")


async def check_channel_membership(bot: Any, user_id: int, channel: str) -> tuple[bool, str]:
    """
    Returns (is_member: bool, error_message: str).
    error_message is empty on success.
    """
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True, ""
        return False, "not_member"
    except TelegramForbiddenError:
        logger.warning("Bot is not a member of channel %s or cannot access it.", channel)
        return True, ""  # Fail open — don't block users if bot can't check
    except TelegramBadRequest as e:
        logger.warning("Bad request checking channel membership: %s", e)
        return True, ""
    except Exception as e:
        logger.warning("Unexpected error checking channel membership: %s", e)
        return True, ""


class FSubMiddleware(BaseMiddleware):
    """
    Checks that the user is a member of the required channel before
    processing any message or callback.

    Skips the check when FSUB_ENABLED is False.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not self._config.fsub_enabled:
            return await handler(event, data)

        # Determine user
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            # Allow fsub:check callback to bypass (so "I've Joined" works)
            if event.data == "fsub:check":
                return await handler(event, data)
            user = event.from_user

        if user is None:
            return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        is_member, _ = await check_channel_membership(bot, user.id, self._config.fsub_channel)

        if is_member:
            return await handler(event, data)

        # Not a member — block and show join prompt
        from app.bot.keyboards.menus import build_fsub_keyboard
        from app.bot.messages.texts import FSUB_REQUIRED

        keyboard = build_fsub_keyboard(
            channel_url=self._config.fsub_channel_url,
            channel_name=self._config.fsub_channel,
        )

        if isinstance(event, Message):
            # Save start param if present
            if event.text and event.text.startswith("/start "):
                param = event.text.split(" ", 1)[1].strip()
                set_pending_start_param(user.id, param)
            await event.answer(FSUB_REQUIRED, reply_markup=keyboard, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("Please join our channel first.", show_alert=True)

        return  # Do not call handler
