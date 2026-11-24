"""
tests/test_fsub.py

Tests for FSub middleware utilities (non-async parts).
"""
import pytest
from app.bot.middlewares.fsub import (
    set_pending_start_param,
    get_and_clear_pending_start_param,
)


class TestPendingStartParam:
    def test_set_and_get(self):
        set_pending_start_param(user_id=1001, param="help")
        result = get_and_clear_pending_start_param(user_id=1001)
        assert result == "help"

    def test_clears_after_get(self):
        set_pending_start_param(user_id=1002, param="help")
        get_and_clear_pending_start_param(user_id=1002)
        result = get_and_clear_pending_start_param(user_id=1002)
        assert result == ""

    def test_empty_param_not_stored(self):
        set_pending_start_param(user_id=1003, param="")
        result = get_and_clear_pending_start_param(user_id=1003)
        assert result == ""

    def test_missing_user_returns_empty(self):
        result = get_and_clear_pending_start_param(user_id=9999)
        assert result == ""

    def test_multiple_users_independent(self):
        set_pending_start_param(user_id=2001, param="help")
        set_pending_start_param(user_id=2002, param="about")
        assert get_and_clear_pending_start_param(2001) == "help"
        assert get_and_clear_pending_start_param(2002) == "about"


class TestFSubCache:
    def test_cache_hit_and_expiry(self):
        import time
        from app.bot.middlewares.fsub import FSubCache
        c = FSubCache(default_ttl=1)
        c.set(user_id=10, is_member=True)
        assert c.get(user_id=10) is True

        time.sleep(1.05)
        # Should be expired
        assert c.get(user_id=10) is None

    def test_cache_invalidate(self):
        from app.bot.middlewares.fsub import FSubCache
        c = FSubCache(default_ttl=60)
        c.set(user_id=11, is_member=True)
        assert c.get(user_id=11) is True
        c.invalidate(11)
        assert c.get(user_id=11) is None


@pytest.mark.asyncio
async def test_fresh_membership_check_bypasses_cache():
    from unittest.mock import AsyncMock, MagicMock
    from app.bot.middlewares.fsub import check_channel_membership, cache

    # Setup mock bot
    mock_bot = MagicMock()
    mock_member = MagicMock()
    mock_member.status = "member"
    mock_bot.get_chat_member = AsyncMock(return_value=mock_member)

    # First set stale negative cache
    cache.set(user_id=999, is_member=False, ttl=60)

    # Without bypass -> returns cached False
    is_member, _ = await check_channel_membership(mock_bot, user_id=999, bypass_cache=False)
    assert not is_member
    mock_bot.get_chat_member.assert_not_called()

    # With bypass_cache=True (e.g. clicking "I've Joined") -> calls API and returns True!
    is_member, _ = await check_channel_membership(mock_bot, user_id=999, bypass_cache=True)
    assert is_member
    mock_bot.get_chat_member.assert_called_once()
