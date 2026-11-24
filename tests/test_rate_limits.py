"""
tests/test_rate_limits.py

Tests for per-user rate limiter.
"""
import time
import pytest

from app.services.rate_limits import RateLimiter


class TestRateLimiter:
    def test_allows_first_request(self):
        limiter = RateLimiter(daily_limit=5, cooldown_seconds=0)
        allowed, reason = limiter.check(user_id=1)
        assert allowed
        assert reason == ""

    def test_records_usage(self):
        limiter = RateLimiter(daily_limit=5, cooldown_seconds=0)
        limiter.record(user_id=1)
        assert limiter.remaining(1) == 4

    def test_blocks_after_daily_limit(self):
        limiter = RateLimiter(daily_limit=3, cooldown_seconds=0)
        for _ in range(3):
            limiter.record(user_id=2)
        allowed, reason = limiter.check(user_id=2)
        assert not allowed
        assert "daily limit" in reason.lower()

    def test_cooldown_blocks_rapid_requests(self):
        limiter = RateLimiter(daily_limit=100, cooldown_seconds=60)
        limiter.record(user_id=3)
        allowed, reason = limiter.check(user_id=3)
        assert not allowed
        assert "wait" in reason.lower()

    def test_unlimited_daily_limit(self):
        limiter = RateLimiter(daily_limit=0, cooldown_seconds=0)
        for _ in range(50):
            limiter.record(user_id=4)
        allowed, _ = limiter.check(user_id=4)
        assert allowed

    def test_different_users_independent(self):
        limiter = RateLimiter(daily_limit=1, cooldown_seconds=0)
        limiter.record(user_id=10)
        allowed, _ = limiter.check(user_id=10)
        assert not allowed
        allowed2, _ = limiter.check(user_id=11)
        assert allowed2  # Different user is not blocked
