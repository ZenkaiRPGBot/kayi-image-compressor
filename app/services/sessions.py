"""
app/services/sessions.py

In-memory session store with TTL-based expiry and session file tracking.
Sessions are NOT persisted across restarts — this is documented behaviour.
"""
from __future__ import annotations

import itertools
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from app.services.cleanup import cleanup_session_files

logger = logging.getLogger(__name__)
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
    input_dimensions: Tuple[int, int] = (0, 0)

    # Output file
    output_file_path: str = ""
    output_format: str = ""
    output_size: int = 0

    # In-flight lock to reject duplicate rapid callback execution
    in_flight: bool = False

    # State machine
    state: str = "idle"   # idle → waiting_choice → waiting_target_input → waiting_form_* → processing → done

    # Historical parameters for 1-tap Retries
    last_mode: str = "auto"              # "auto", "preset", "target"
    last_preset: Optional[str] = None
    last_target_kb: Optional[int] = None
    last_quality: int = 75
    last_allow_resize: bool = False
    last_output_format: str = ""

    # Unified Advanced Settings (applies to both Auto Compress & Target Size)
    selected_format: str = ""           # "" = keep original, or "JPEG", "PNG", "WEBP"
    selected_preset: str = "balanced"   # "best_quality", "balanced", "smallest", "lossless"
    strip_metadata: bool = True
    dimension_mode: str = "auto"        # "auto", "100", "75", "50", "25", "custom"
    scale_percent: float = 1.0          # 1.0 = 100%, 0.75 = 75%, etc.
    exact_width: int = 0
    exact_height: int = 0
    max_width: int = 0
    max_height: int = 0
    fit_mode: str = "fit"               # "fit", "pad", "crop"

    def touch(self) -> None:
        self.last_accessed = time.monotonic()

    def is_expired(self, ttl_seconds: int) -> bool:
        return (time.monotonic() - self.last_accessed) >= ttl_seconds


class SessionStore:
    """
    Thread-safe in-memory session store with TTL pruning and capacity bounding.
    """

    def __init__(self, ttl_seconds: int = 600, max_sessions: int = 50) -> None:
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._sessions: Dict[str, UserSession] = {}

    def create(self, user_id: int) -> UserSession:
        # Enforce session capacity
        if len(self._sessions) >= self._max_sessions:
            self.cleanup()
            if len(self._sessions) >= self._max_sessions:
                # Evict oldest session
                oldest_sid = min(self._sessions.keys(), key=lambda k: self._sessions[k].created_at)
                self.delete(oldest_sid)

        session_id = uuid.uuid4().hex
        session = UserSession(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[UserSession]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired(self._ttl):
            self.delete(session_id)
            return None
        session.touch()
        return session

    def delete(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            cleanup_session_files(session.input_file_path, session.output_file_path)

    def cleanup(self) -> int:
        """Remove all expired sessions and clean up their files. Returns count removed."""
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired(self._ttl)
        ]
        for sid in expired:
            self.delete(sid)
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
