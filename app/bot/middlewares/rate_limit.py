"""
app/bot/middlewares/rate_limit.py

Rate limiting middleware — applies per-user cooldown and daily limits
only for image upload messages (not for commands or callbacks).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message


class RateLimitMiddleware(BaseMiddleware):
    """
    Applies rate limiting to image/document uploads only.
    Commands and callbacks are not rate-limited here.
    """

    def __init__(self, rate_limiter: Any) -> None:
        self._limiter = rate_limiter
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        # Only apply to photo/document messages
        if not (event.photo or event.document):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        allowed, reason = self._limiter.check(user.id)
        if not allowed:
            from app.bot.messages.texts import RATE_LIMITED
            await event.answer(RATE_LIMITED.format(reason=reason), parse_mode="HTML")
            return

        return await handler(event, data)
