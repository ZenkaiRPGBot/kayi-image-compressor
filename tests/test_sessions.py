"""
tests/test_sessions.py

Tests for the in-memory session store.
"""
import time
import pytest

from app.services.sessions import SessionStore, UserSession


class TestSessionStore:
    def test_create_and_get(self):
        store = SessionStore(ttl_seconds=60)
        session = store.create(user_id=1001)
        assert session.user_id == 1001
        assert session.session_id

        retrieved = store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_missing_session_returns_none(self):
        store = SessionStore(ttl_seconds=60)
        assert store.get("nonexistent") is None

    def test_delete(self):
        store = SessionStore(ttl_seconds=60)
        session = store.create(user_id=1002)
        store.delete(session.session_id)
        assert store.get(session.session_id) is None

    def test_expired_session_returns_none(self):
        store = SessionStore(ttl_seconds=0)  # Expires immediately
        session = store.create(user_id=1003)
        time.sleep(0.01)
        assert store.get(session.session_id) is None

    def test_cleanup_removes_expired(self):
        store = SessionStore(ttl_seconds=0)
        store.create(user_id=1004)
        store.create(user_id=1005)
        time.sleep(0.01)
        removed = store.cleanup()
        assert removed == 2
        assert store.count() == 0

    def test_get_by_user(self):
        store = SessionStore(ttl_seconds=60)
        s1 = store.create(user_id=2001)
        s2 = store.create(user_id=2001)
        result = store.get_by_user(2001)
        assert result is not None
        assert result.session_id == s2.session_id  # Most recent

    def test_count(self):
        store = SessionStore(ttl_seconds=60)
        assert store.count() == 0
        store.create(user_id=3001)
        store.create(user_id=3002)
        assert store.count() == 2

    def test_session_ownership(self):
        store = SessionStore(ttl_seconds=60)
        s = store.create(user_id=9001)
        assert s.user_id == 9001
