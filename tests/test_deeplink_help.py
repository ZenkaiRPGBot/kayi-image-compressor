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
