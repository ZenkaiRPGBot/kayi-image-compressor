"""
app/bot/middlewares/fsub.py

Force-subscribe middleware for Kayi Image Compressor.
Matches the official, established FSub architecture of the Kayi Bots ecosystem.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ParseMode
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger("fsub")

# ==============================================================================
# UI COPY & KEYBOARD
# ==============================================================================

# Pending deep-link start parameter tracking across FSub prompts
_PENDING_PARAMS: dict[int, tuple[str, float]] = {}
PENDING_PARAM_TTL = 300.0  # 5 minutes


def set_pending_start_param(user_id: int, param: str) -> None:
    if param:
        _PENDING_PARAMS[user_id] = (param, time.time() + PENDING_PARAM_TTL)


def get_and_clear_pending_start_param(user_id: int) -> str:
    val = _PENDING_PARAMS.pop(user_id, None)
    if not val:
        return ""
    param, expiry = val
    if time.time() > expiry:
        return ""
    return param


FSUB_PROMPT_TEXT = (
    "<b>Join Kayi Bots to Continue</b>\n\n"
    "To use Kayi Image Compressor, please join our official channel.\n\n"
    "Get announcements, new features, and important service updates.\n\n"
    "Once you've joined, tap <b>I've Joined</b> to verify your membership."
)


def build_fsub_keyboard(channel_url: str = "https://t.me/KayiBots", channel_name: str = "@KayiBots") -> InlineKeyboardMarkup:
    """Builds native Telegram inline keyboard with Join URL and I've Joined callback."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📢 Join {channel_name}",
                url=channel_url,
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ I've Joined",
                callback_data="fsub:verify",
                style="success",
            )
        ]
    ])


# ==============================================================================
# IN-MEMORY TTL CACHE
# ==============================================================================

class FSubCache:
    """
    In-memory per-user membership cache with configurable time-to-live (TTL).
    Reduces latency and prevents excessive Telegram getChatMember calls.
    """
    def __init__(self, default_ttl: int = 45):
        self.default_ttl = default_ttl
        self._store: dict[int, tuple[bool, float]] = {}

    def get(self, user_id: int) -> bool | None:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        is_member, expires_at = entry
        if time.monotonic() < expires_at:
            return is_member
        self._store.pop(user_id, None)
        return None

    def set(self, user_id: int, is_member: bool, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self.default_ttl
        self._store[user_id] = (is_member, time.monotonic() + effective_ttl)

    def invalidate(self, user_id: int) -> None:
        self._store.pop(user_id, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


cache = FSubCache()


# ==============================================================================
# MEMBERSHIP CHECKER
# ==============================================================================

async def check_channel_membership(
    bot: Bot,
    user_id: int,
    channel: str = "@KayiBots",
    bypass_cache: bool = False,
    timeout: float = 5.0,
) -> tuple[bool, str]:
    """
    Queries Telegram getChatMember with fail-closed semantics.
    """
    if not bypass_cache:
        cached = cache.get(user_id)
        if cached is not None:
            return cached, "cached"

    try:
        member = await asyncio.wait_for(
            bot.get_chat_member(chat_id=channel, user_id=user_id),
            timeout=timeout,
        )
        status = member.status

        if status in ("creator", "administrator", "member"):
            is_member = True
        elif status == "restricted":
            is_member = getattr(member, "is_member", False)
        else:
            is_member = False

        cache.set(user_id, is_member)

        if is_member:
            logger.info("FSUB_ALLOW user_id=%s status=%s channel=%s", user_id, status, channel)
        else:
            logger.info("FSUB_DENY user_id=%s status=%s channel=%s", user_id, status, channel)

        return is_member, status

    except asyncio.TimeoutError:
        logger.warning("FSUB_TIMEOUT user_id=%s channel=%s timeout=%ss", user_id, channel, timeout)
        return False, "timeout"
    except (TelegramBadRequest, TelegramForbiddenError) as tg_err:
        logger.warning("FSUB_TG_ERROR user_id=%s channel=%s error=%s: %s", user_id, channel, type(tg_err).__name__, tg_err)
        return False, f"error:{type(tg_err).__name__}"
    except Exception as exc:
        logger.error("FSUB_UNEXPECTED_ERROR user_id=%s channel=%s error=%s: %s", user_id, channel, type(exc).__name__, exc)
        return False, f"error:{type(exc).__name__}"


# ==============================================================================
# ENFORCEMENT MIDDLEWARE
# ==============================================================================

class FSubMiddleware(BaseMiddleware):
    """
    Outer middleware enforcing mandatory channel membership across all commands,
    messages (including image uploads), and callback queries.
    """
    def __init__(self, config: Any):
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

        user = data.get("event_from_user")
        bot: Bot | None = data.get("bot")

        if not user or not bot:
            return await handler(event, data)

        # Narrow whitelist: 'fsub:verify' must pass to verification handler
        if isinstance(event, CallbackQuery) and event.data == "fsub:verify":
            return await handler(event, data)

        is_member, _ = await check_channel_membership(
            bot=bot,
            user_id=user.id,
            channel=self._config.fsub_channel,
            bypass_cache=False,
            timeout=self._config.fsub_timeout,
        )

        if is_member:
            return await handler(event, data)

        # Non-member blocked
        if isinstance(event, Message):
            if event.chat and event.chat.type != "private":
                return None

            msg_text = getattr(event, "text", None)
            if msg_text:
                parts = str(msg_text).strip().split(maxsplit=1)
                if len(parts) > 1 and parts[0].lower().startswith("/start") and parts[1].strip().lower() == "help":
                    set_pending_start_param(user.id, "help")

            await event.answer(
                text=FSUB_PROMPT_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=build_fsub_keyboard(self._config.fsub_channel_url, self._config.fsub_channel),
                disable_web_page_preview=True,
            )
            return None

        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(
                    f"Please join {self._config.fsub_channel} to use Kayi Image Compressor.",
                    show_alert=True,
                )
            except Exception:
                pass

            if event.message:
                try:
                    await event.message.edit_text(
                        text=FSUB_PROMPT_TEXT,
                        parse_mode=ParseMode.HTML,
                        reply_markup=build_fsub_keyboard(self._config.fsub_channel_url, self._config.fsub_channel),
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass
            return None

        return None
