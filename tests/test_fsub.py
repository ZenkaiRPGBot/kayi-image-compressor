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
