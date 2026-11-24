"""
app/services/sessions.py

In-memory session store with TTL-based expiry.
Sessions are NOT persisted across restarts — this is documented behaviour.
"""
from __future__ import annotations

import time
import itertools
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

_seq_counter = itertools.count()


@dataclass
class UserSession:
    session_id: str
    user_id: int
    created_at: float = field(default_factory=time.monotonic)
    seq: int = field(default_factory=lambda: next(_seq_counter))
    last_accessed: float = field(default_factory=time.monotonic)

    # Input file
    input_file_id: str = ""
    input_file_path: str = ""
    input_file_size: int = 0
    input_format: str = ""
    input_dimensions: tuple = (0, 0)

    # Output file (after compression)
    output_file_path: str = ""
    output_format: str = ""

    # State machine
    state: str = "idle"   # idle → waiting_image → processing → done → error
    pending_target_kb: Optional[int] = None
    pending_preset: Optional[str] = None

    def touch(self) -> None:
        self.last_accessed = time.monotonic()

    def is_expired(self, ttl_seconds: int) -> bool:
        return (time.monotonic() - self.last_accessed) > ttl_seconds


class SessionStore:
    """
    Thread-safe (GIL-protected) in-memory session store.

    Sessions expire after `ttl_seconds` of inactivity and are pruned
    lazily on access and periodically via cleanup().
    """

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._sessions: Dict[str, UserSession] = {}

    def create(self, user_id: int) -> UserSession:
        session_id = uuid.uuid4().hex
        session = UserSession(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[UserSession]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired(self._ttl):
            del self._sessions[session_id]
            return None
        session.touch()
        return session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def cleanup(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired(self._ttl)
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def count(self) -> int:
        return len(self._sessions)

    def get_by_user(self, user_id: int) -> Optional[UserSession]:
        """Return the most recent active session for a user."""
        candidates = [
            s for s in self._sessions.values()
            if s.user_id == user_id and not s.is_expired(self._ttl)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: (s.created_at, s.seq))
