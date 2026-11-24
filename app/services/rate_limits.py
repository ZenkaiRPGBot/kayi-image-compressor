"""
app/services/rate_limits.py

Per-user rate limiting — daily image limit and per-request cooldown.
State is in-memory only and resets on restart (documented).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class UserCounter:
    count: int = 0
    day_start: float = field(default_factory=time.time)
    last_request: float = 0.0

    def reset_if_new_day(self) -> None:
        # Simple 24h rolling window
        if time.time() - self.day_start >= 86400:
            self.count = 0
            self.day_start = time.time()


class RateLimiter:
    """
    Tracks per-user daily usage and minimum cooldown between requests.

    daily_limit: Max images per user per 24h (0 = unlimited)
    cooldown_seconds: Minimum seconds between requests per user
    """

    def __init__(self, daily_limit: int = 20, cooldown_seconds: float = 3.0) -> None:
        self._daily_limit = daily_limit
        self._cooldown = cooldown_seconds
        self._counters: Dict[int, UserCounter] = {}

    def _get(self, user_id: int) -> UserCounter:
        if user_id not in self._counters:
            self._counters[user_id] = UserCounter()
        counter = self._counters[user_id]
        counter.reset_if_new_day()
        return counter

    def check(self, user_id: int) -> tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        Call before accepting a new compression job.
        """
        counter = self._get(user_id)
        now = time.time()

        # Cooldown check
        if counter.last_request > 0 and (now - counter.last_request) < self._cooldown:
            remaining = self._cooldown - (now - counter.last_request)
            return False, f"Please wait {remaining:.1f}s before sending another image."

        # Daily limit check
        if self._daily_limit > 0 and counter.count >= self._daily_limit:
            return False, (
                f"You've reached your daily limit of {self._daily_limit} compressions. "
                "Limits reset every 24 hours."
            )

        return True, ""

    def record(self, user_id: int) -> None:
        """Call after accepting a compression job."""
        counter = self._get(user_id)
        counter.count += 1
        counter.last_request = time.time()

    def remaining(self, user_id: int) -> int:
        """Return remaining compressions today."""
        counter = self._get(user_id)
        if self._daily_limit <= 0:
            return 999
        return max(0, self._daily_limit - counter.count)
