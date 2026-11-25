"""
tests/test_deeplink_help.py

Tests for /start help deep-link parameter handling.
Verifies the routing logic without making Telegram API calls.
"""
import pytest
from app.bot.middlewares.fsub import (
    set_pending_start_param,
    get_and_clear_pending_start_param,
)


class TestDeepLinkHelp:
    def test_help_param_preserved_through_fsub(self):
        """
        Simulate FSub middleware saving 'help' param and start handler retrieving it.
        """
        user_id = 5001
        # FSub middleware saves the param when it blocks the user
        set_pending_start_param(user_id=user_id, param="help")
        # After user joins, /start handler retrieves it
        param = get_and_clear_pending_start_param(user_id=user_id)
        assert param == "help"

    def test_non_help_param_preserved(self):
        user_id = 5002
        set_pending_start_param(user_id=user_id, param="ref_12345")
        param = get_and_clear_pending_start_param(user_id=user_id)
        assert param == "ref_12345"

    def test_empty_param_not_treated_as_help(self):
        user_id = 5003
        set_pending_start_param(user_id=user_id, param="")
        param = get_and_clear_pending_start_param(user_id=user_id)
        assert param != "help"
        assert param == ""

    def test_param_cleared_after_retrieval(self):
        """Deep-link params must only be acted on once."""
        user_id = 5004
        set_pending_start_param(user_id=user_id, param="help")
        get_and_clear_pending_start_param(user_id=user_id)
        # Second retrieval must return empty
        assert get_and_clear_pending_start_param(user_id=user_id) == ""

    @pytest.mark.asyncio
    async def test_plain_help_command_saved_when_blocked_by_fsub(self):
        """A plain /help blocked by FSub saves 'help' so joining shows Help."""
        from unittest.mock import AsyncMock, MagicMock
        from aiogram.types import Message
        from app.bot.middlewares.fsub import FSubMiddleware, cache

        user_id = 5505
        cache.invalidate(user_id)

        bot = MagicMock()
        member = MagicMock()
        member.status = "left"
        bot.get_chat_member = AsyncMock(return_value=member)

        config = MagicMock(
            fsub_enabled=True,
            fsub_channel="@KayiBots",
            fsub_channel_url="https://t.me/KayiBots",
            fsub_cache_ttl=45,
            fsub_timeout=5.0,
            owner_id=986380678,
        )

        user = MagicMock(id=user_id, username="tester", first_name="Test")
        message = MagicMock(spec=Message)
        message.from_user = user
        message.chat = MagicMock(type="private")
        message.text = "/help"
        message.answer = AsyncMock()

        handler = AsyncMock()
        middleware = FSubMiddleware(config)
        await middleware(handler, message, {"bot": bot, "event_from_user": user})

        handler.assert_not_called()
        message.answer.assert_awaited_once()
        assert get_and_clear_pending_start_param(user_id=user_id) == "help"
