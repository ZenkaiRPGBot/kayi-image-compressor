"""
app/bot/handlers/usage.py

Handles /usage, /render, and /ping commands.
Collects on-demand process, storage, and Render hosting metrics
matching the official Kayi Bots ecosystem standard.
"""
from __future__ import annotations

import asyncio
import html
import logging
import time
from datetime import datetime, timezone

import psutil
from aiogram import Router, F, Bot
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
)

from app.config import Config
from app.services.cleanup import get_temp_storage_usage
from app.services.sessions import SessionStore

logger = logging.getLogger(__name__)
router = Router(name="usage")

BOT_START_TIME = datetime.now(timezone.utc)


def mask_email(email_str: str) -> str:
    """Masks email address to protect privacy (e.g. us***@domain.com)."""
    if not email_str or "@" not in email_str:
        return "[Not Configured]"
    parts = email_str.split("@", 1)
    user_part = parts[0]
    domain_part = parts[1]
    if len(user_part) <= 2:
        masked_user = user_part[0] + "***"
    else:
        masked_user = user_part[:2] + "***"
    return f"{masked_user}@{domain_part}"


def is_owner(user_id: int | None, config: Config) -> bool:
    """Fail-closed owner authorization check."""
    return bool(config.owner_id and user_id and user_id == config.owner_id)


def get_uptime_string() -> str:
    now = datetime.now(timezone.utc)
    uptime_sec = int((now - BOT_START_TIME).total_seconds())
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def get_process_memory_mb() -> float:
    try:
        return psutil.Process().memory_info().rss / (1024.0 * 1024.0)
    except Exception:
        return 0.0


def get_process_cpu_percent() -> float:
    try:
        return psutil.Process().cpu_percent(interval=0.05)
    except Exception:
        return 0.0


async def measure_gateway_latency(bot: Bot) -> float:
    t0 = time.perf_counter()
    try:
        await bot.get_me()
    except Exception:
        pass
    return (time.perf_counter() - t0) * 1000.0


async def build_usage_card_text(
    bot: Bot, config: Config, sessions: SessionStore
) -> tuple[str, InlineKeyboardMarkup]:
    now = datetime.now(timezone.utc)
    uptime_str = get_uptime_string()

    # Render Monthly Free Instance Hours (750h cap)
    session_hours = (now - BOT_START_TIME).total_seconds() / 3600.0
    total_used_hours = min(750.0, config.render_used_hours + session_hours)
    remaining_hours = max(0.0, 750.0 - total_used_hours)
    used_pct = min(100.0, (total_used_hours / 750.0) * 100.0)
    days_left_capacity = remaining_hours / 24.0

    # Process-level metrics (on-demand)
    cpu_pct = get_process_cpu_percent()
    mem_mb = get_process_memory_mb()
    mem_pct = min(100.0, (mem_mb / 512.0) * 100.0)
    temp_bytes, temp_files = get_temp_storage_usage()
    temp_mb = temp_bytes / (1024.0 * 1024.0)
    max_storage_mb = config.max_storage_budget_bytes / (1024.0 * 1024.0)

    ping_ms = await measure_gateway_latency(bot)

    active_jobs = sessions.active_jobs_count()
    active_sessions = sessions.count()
    queued_jobs = max(0, sum(1 for s in sessions._sessions.values() if s.state == "processing") - active_jobs)
    max_mp = config.max_image_pixels / 1_000_000

    email_display = config.render_email if config.render_email else "Not Set"

    text = (
        "<b>Kayi Image Compressor — Host & Service Metrics</b>\n\n"
        "<b>Render Instance & Account:</b>\n"
        "• <b>Cloud:</b> Render (Frankfurt, EU-Central)\n"
        f"• <b>Account Email:</b> <code>{html.escape(email_display)}</code>\n"
        f"• <b>Service Name:</b> <code>{html.escape(config.render_service_name)}</code>\n"
        f"• <b>Repository:</b> <code>{html.escape(config.render_repo)}</code>\n"
        f"• <b>Bot Uptime:</b> <code>{uptime_str}</code>\n"
        f"• <b>Monthly Hours (750h):</b> <code>{total_used_hours:.1f}h / 750h ({used_pct:.1f}%)</code>\n"
        f"• <b>Remaining Free:</b> <code>{remaining_hours:.1f}h (~{days_left_capacity:.1f} days)</code>\n\n"
        "<b>Process Resources (On-Demand):</b>\n"
        f"• <b>Process CPU:</b> <code>{cpu_pct:.1f}%</code>\n"
        f"• <b>Process RAM:</b> <code>{mem_mb:.1f} MB / 512 MB ({mem_pct:.1f}%)</code>\n"
        f"• <b>Temp Storage:</b> <code>{temp_mb:.2f} MB / {max_storage_mb:.0f} MB ({temp_files} files)</code>\n\n"
        "<b>Compression Engine & Limits:</b>\n"
        f"• <b>Active Jobs:</b> <code>{active_jobs} / {config.max_concurrent_jobs}</code>\n"
        f"• <b>Queued Jobs:</b> <code>{queued_jobs} / {config.max_queue_size}</code>\n"
        f"• <b>Active Sessions:</b> <code>{active_sessions}</code>\n"
        f"• <b>Upload / Pixel Cap:</b> <code>{config.max_upload_bytes // (1024 * 1024)} MB / {max_mp:.0f} MP</code>\n"
        f"• <b>Telegram API Ping:</b> <code>{ping_ms:.1f} ms</code>"
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Refresh Metrics", callback_data="usage:refresh", style="primary"
                )
            ]
        ]
    )
    return text, markup


def _build_ping_message(bot_ms: float, api_ms: float) -> tuple[str, InlineKeyboardMarkup]:
    uptime = get_uptime_string()
    text = (
        "<b>Pong!</b> ⚡\n\n"
        f"<b>Bot Responsiveness:</b> <code>{bot_ms:.2f} ms</code>\n"
        f"<b>Telegram API Latency:</b> <code>{api_ms:.1f} ms</code>\n\n"
        f"<b>Uptime:</b> <code>{uptime}</code>"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Check Ping", callback_data="ping:refresh", style="primary"
                )
            ]
        ]
    )
    return text, markup


@router.message(Command("usage"))
@router.message(Command("render"))
async def cmd_usage(
    message: Message, bot: Bot, config: Config, sessions: SessionStore
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not is_owner(user_id, config):
        await message.reply("Access restricted to bot owner.")
        return

    text, markup = await build_usage_card_text(bot, config, sessions)
    await message.answer(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)


@router.callback_query(F.data == "usage:refresh")
async def cb_usage_refresh(
    callback: CallbackQuery, bot: Bot, config: Config, sessions: SessionStore
) -> None:
    user_id = callback.from_user.id if callback.from_user else None
    if not is_owner(user_id, config):
        await callback.answer("Access restricted to bot owner.", show_alert=True)
        return

    text, markup = await build_usage_card_text(bot, config, sessions)
    try:
        await callback.message.edit_text(
            text=text, parse_mode=ParseMode.HTML, reply_markup=markup
        )
    except Exception:
        pass
    await callback.answer("Metrics refreshed")


@router.message(Command("ping"))
async def cmd_ping(message: Message, bot: Bot) -> None:
    t_start = time.perf_counter()
    api_ms = await measure_gateway_latency(bot)
    bot_ms = max(0.01, (time.perf_counter() - t_start) * 1000.0 - api_ms)

    text, markup = _build_ping_message(bot_ms, api_ms)
    await message.reply(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)


@router.callback_query(F.data == "ping:refresh")
async def cb_ping_refresh(callback: CallbackQuery, bot: Bot) -> None:
    t_start = time.perf_counter()
    api_ms = await measure_gateway_latency(bot)
    bot_ms = max(0.01, (time.perf_counter() - t_start) * 1000.0 - api_ms)

    text, markup = _build_ping_message(bot_ms, api_ms)
    try:
        await callback.message.edit_text(
            text=text, parse_mode=ParseMode.HTML, reply_markup=markup
        )
    except Exception:
        pass
    await callback.answer("Ping refreshed")


async def register_bot_commands(bot: Bot, config: Config) -> None:
    """Registers public and owner commands in Telegram's menu."""
    public_commands = [
        BotCommand(command="start", description="Start bot & instructions"),
        BotCommand(command="help", description="How to use & format options"),
        BotCommand(command="compress", description="Compress an image"),
        BotCommand(command="privacy", description="Privacy and data policy"),
        BotCommand(command="ping", description="Check bot latency and uptime"),
    ]
    owner_commands = public_commands + [
        BotCommand(
            command="usage", description="Render hosting & account usage (Owner)"
        )
    ]
    try:
        await bot.set_my_commands(public_commands, scope=BotCommandScopeDefault())
        if config.owner_id:
            try:
                await bot.set_my_commands(
                    owner_commands,
                    scope=BotCommandScopeChat(chat_id=config.owner_id),
                )
            except Exception as e:
                logger.warning("Could not register owner commands for %s: %s", config.owner_id, e)
        logger.info("Bot commands registered with Telegram (/start, /help, /compress, /privacy, /ping, /usage).")
    except Exception as e:
        logger.warning("Could not register default bot commands: %s", e)
