"""
app/services/restart_notify.py

Kayi Bots startup & restart notification system.
Matches the established format across Temp Mail Bot, Image to Link Bot, and Kayi PDF Bot:
- Branded HTML heading with green indicator
- Bulleted recent changes from restart_reason.txt or git commit log
- IST timestamp
- Owner + optional log channel delivery
- Non-blocking background execution and per-commit duplicate suppression
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from aiogram import Bot
from aiogram.enums import ParseMode

from app.config import Config

logger = logging.getLogger(__name__)

BRAND_NAME = "Kayi Image Compressor"
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_CHANGES = ["Bug fixes and performance improvements"]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_COMMIT_PREFIXES = (
    "feat:",
    "fix:",
    "chore:",
    "refactor:",
    "perf:",
    "docs:",
    "style:",
    "test:",
    "ui:",
    "build:",
)


def current_commit(root: Path | None = None) -> str:
    """Return Render's deployed commit or local git HEAD."""
    render_commit = os.getenv("RENDER_GIT_COMMIT", "").strip()
    if render_commit:
        return render_commit
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root or _PROJECT_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
    except Exception:
        return ""


def latest_changes(
    root: Path | None = None,
    reason_path: Path | None = None,
) -> list[str]:
    """Read restart_reason.txt first (consumed on read), then latest git commit."""
    base = Path(root or _PROJECT_ROOT)
    reason = Path(reason_path) if reason_path is not None else base / "restart_reason.txt"
    if reason.exists():
        try:
            content = reason.read_text(encoding="utf-8").strip()
            reason.unlink(missing_ok=True)
            if content:
                return [
                    line.strip("-•* ").strip()
                    for line in content.splitlines()
                    if line.strip()
                ]
        except Exception:
            pass

    try:
        raw = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s%n%b"],
            cwd=str(base),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
        lines = [line.strip("-•* ").strip() for line in raw.splitlines() if line.strip()]
        cleaned: list[str] = []
        for line in lines:
            for prefix in _COMMIT_PREFIXES:
                if line.lower().startswith(prefix):
                    line = line[len(prefix) :].strip()
                    break
            if (
                line
                and len(line) > 3
                and not line.startswith("Co-authored-by:")
                and not line.startswith("Signed-off-by:")
            ):
                cleaned.append(line[0].upper() + line[1:])
            if len(cleaned) >= 3:
                break
        if cleaned:
            return cleaned
    except Exception:
        pass

    return list(DEFAULT_CHANGES)


class RestartNotifier:
    """Send at most one branded startup alert per process and deployed commit."""

    def __init__(
        self,
        bot: Bot,
        *,
        owner_id: int = 0,
        log_channel_id: int = 0,
        brand_name: str = BRAND_NAME,
        state_path: Path | None = None,
        root: Path | None = None,
        reason_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.bot = bot
        self.owner_id = int(owner_id or 0)
        self.log_channel_id = int(log_channel_id or 0)
        self.brand_name = brand_name
        self.root = Path(root or _PROJECT_ROOT)
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else Path(tempfile.gettempdir()) / "kayi_image_compressor_restart_state.json"
        )
        self.reason_path = (
            Path(reason_path)
            if reason_path is not None
            else self.root / "restart_reason.txt"
        )
        self.clock = clock or (lambda: datetime.now(IST))
        self._lock = asyncio.Lock()
        self._attempted = False

    def targets(self) -> list[int]:
        targets: list[int] = []
        if self.owner_id:
            targets.append(self.owner_id)
        if self.log_channel_id and self.log_channel_id not in targets:
            targets.append(self.log_channel_id)
        return targets

    def _read_last_commit(self) -> str:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        value = payload.get("last_notified_commit") if isinstance(payload, dict) else ""
        return value if isinstance(value, str) else ""

    def _write_last_commit(self, commit: str) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.state_path.with_name(self.state_path.name + ".tmp")
            tmp_path.write_text(
                json.dumps({"last_notified_commit": commit}),
                encoding="utf-8",
            )
            tmp_path.replace(self.state_path)
        except OSError as exc:
            logger.warning("Could not persist restart state: %s", type(exc).__name__)

    async def notify_once(self) -> bool:
        """Deliver startup notification once per process without blocking startup."""
        async with self._lock:
            if self._attempted:
                return False
            self._attempted = True
            try:
                return await self._notify()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Restart notification failed")
                return False

    async def _notify(self) -> bool:
        targets = self.targets()
        if not targets:
            logger.info("Restart notification skipped: OWNER_ID/LOG_CHANNEL_ID not set.")
            return False

        has_reason = self.reason_path.exists()
        commit = current_commit(self.root)
        if not has_reason and commit and self._read_last_commit() == commit:
            logger.info(
                "Restart notification skipped: commit %s already notified.", commit[:7]
            )
            return False

        changes = latest_changes(self.root, self.reason_path)
        formatted = "\n".join(f"• {html.escape(c)}" for c in changes)
        now_str = self.clock().astimezone(IST).strftime("%I:%M %p IST · %b %d")
        content = (
            f"<b>{html.escape(self.brand_name)} Online 🟢</b>\n\n"
            "<b>Changes in this Update:</b>\n"
            f"{formatted}\n\n"
            f"<b>Time:</b> <code>{now_str}</code>"
        )

        delivered = 0
        for chat_id in targets:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    parse_mode=ParseMode.HTML,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Could not notify %s: %s", chat_id, type(exc).__name__)
            else:
                delivered += 1
                logger.info("Sent restart notification to %s", chat_id)

        if delivered and commit:
            self._write_last_commit(commit)
        return delivered > 0


def build_restart_notifier(bot: Bot, config: Config) -> RestartNotifier:
    return RestartNotifier(
        bot,
        owner_id=config.owner_id,
        log_channel_id=config.log_channel_id,
    )
