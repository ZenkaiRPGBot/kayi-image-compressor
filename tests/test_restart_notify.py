"""
tests/test_restart_notify.py

Tests for Kayi Image Compressor startup & restart notification service.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ParseMode

from app.services.restart_notify import (
    BRAND_NAME,
    DEFAULT_CHANGES,
    IST,
    RestartNotifier,
    build_restart_notifier,
    current_commit,
    latest_changes,
)


def _mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def test_targets_dedup_and_skip_zero() -> None:
    bot = _mock_bot()
    assert RestartNotifier(bot, owner_id=0, log_channel_id=0).targets() == []
    assert RestartNotifier(bot, owner_id=123, log_channel_id=123).targets() == [123]
    assert RestartNotifier(bot, owner_id=123, log_channel_id=-100456).targets() == [
        123,
        -100456,
    ]


@pytest.mark.asyncio
async def test_notify_skips_without_targets(tmp_path: Path) -> None:
    bot = _mock_bot()
    notifier = RestartNotifier(
        bot,
        owner_id=0,
        log_channel_id=0,
        state_path=tmp_path / "state.json",
        root=tmp_path,
        reason_path=tmp_path / "restart_reason.txt",
    )
    assert await notifier.notify_once() is False
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_uses_restart_reason_and_ist_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123456789")
    reason = tmp_path / "restart_reason.txt"
    reason.write_text("- Fix target size curve\n• Tighten <owner> guard\n", encoding="utf-8")

    fixed_utc = datetime(2026, 11, 25, 3, 45, tzinfo=timezone.utc)  # 09:15 AM IST · Nov 25
    bot = _mock_bot()
    notifier = RestartNotifier(
        bot,
        owner_id=111,
        log_channel_id=-100222,
        state_path=tmp_path / "state.json",
        root=tmp_path,
        reason_path=reason,
        clock=lambda: fixed_utc,
    )

    sent = await notifier.notify_once()
    assert sent is True
    assert not reason.exists()  # consumed on read
    assert bot.send_message.await_count == 2

    first_kwargs = bot.send_message.await_args_list[0].kwargs
    assert first_kwargs["chat_id"] == 111
    assert first_kwargs["parse_mode"] == ParseMode.HTML
    assert "reply_markup" not in first_kwargs
    text = first_kwargs["text"]
    assert f"<b>{BRAND_NAME} Online 🟢</b>" in text
    assert "<b>Changes in this Update:</b>" in text
    assert "• Fix target size curve" in text
    assert "• Tighten &lt;owner&gt; guard" in text
    assert "<b>Time:</b> <code>09:15 AM IST · Nov 25</code>" in text

    # Second call on the same instance is ignored by in-process guard
    assert await notifier.notify_once() is False
    assert bot.send_message.await_count == 2

    # Fresh instance with identical commit is deduplicated via persisted state
    bot2 = _mock_bot()
    notifier2 = RestartNotifier(
        bot2,
        owner_id=111,
        log_channel_id=-100222,
        state_path=tmp_path / "state.json",
        root=tmp_path,
        reason_path=reason,
    )
    assert await notifier2.notify_once() is False
    bot2.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_reason_overrides_commit_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "samecommit999")
    state_path = tmp_path / "state.json"
    state_path.write_text('{"last_notified_commit": "samecommit999"}', encoding="utf-8")
    reason = tmp_path / "restart_reason.txt"
    reason.write_text("Manual restart check", encoding="utf-8")

    bot = _mock_bot()
    notifier = RestartNotifier(
        bot,
        owner_id=111,
        state_path=state_path,
        root=tmp_path,
        reason_path=reason,
    )
    assert await notifier.notify_once() is True
    assert bot.send_message.await_count == 1
    assert "Manual restart check" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_notify_partial_and_total_failure_resilience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "failcommit1")
    state_path = tmp_path / "state.json"

    # Total failure: returns False and does NOT record commit
    bot_all_fail = _mock_bot()
    bot_all_fail.send_message.side_effect = RuntimeError("network error")
    notifier_fail = RestartNotifier(
        bot_all_fail,
        owner_id=111,
        log_channel_id=-100222,
        state_path=state_path,
        root=tmp_path,
        reason_path=tmp_path / "restart_reason.txt",
    )
    assert await notifier_fail.notify_once() is False
    assert not state_path.exists()

    # Partial failure: owner fails, log channel succeeds -> returns True and records commit
    bot_partial = _mock_bot()
    bot_partial.send_message.side_effect = [RuntimeError("blocked"), MagicMock()]
    notifier_partial = RestartNotifier(
        bot_partial,
        owner_id=111,
        log_channel_id=-100222,
        state_path=state_path,
        root=tmp_path,
        reason_path=tmp_path / "restart_reason.txt",
    )
    assert await notifier_partial.notify_once() is True
    assert "failcommit1" in state_path.read_text(encoding="utf-8")


def test_latest_changes_git_cleanup_and_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda *args, **kwargs: (
            "feat: align command scopes\n"
            "- add startup notification\n"
            "Signed-off-by: Dev <dev@example.com>\n"
            "Co-authored-by: Other <o@example.com>\n"
        ),
    )
    changes = latest_changes(root=tmp_path, reason_path=tmp_path / "missing.txt")
    assert changes == ["Align command scopes", "Add startup notification"]

    def _boom(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(subprocess, "check_output", _boom)
    assert latest_changes(root=tmp_path, reason_path=tmp_path / "missing.txt") == DEFAULT_CHANGES

    monkeypatch.setenv("RENDER_GIT_COMMIT", "")
    assert current_commit(root=tmp_path) == ""


def test_build_restart_notifier_uses_config() -> None:
    bot = _mock_bot()
    cfg = MagicMock(owner_id=986380678, log_channel_id=-100999)
    notifier = build_restart_notifier(bot, cfg)
    assert notifier.owner_id == 986380678
    assert notifier.log_channel_id == -100999
    assert notifier.brand_name == BRAND_NAME
    assert IST.utcoffset(None).total_seconds() == 19800
