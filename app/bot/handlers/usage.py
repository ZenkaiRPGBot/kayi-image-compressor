"""
app/bot/handlers/usage.py

Handles /usage, /render, and /ping commands.
Tracks Render Free Tier hours (750h limit), RAM consumption, uptime,
Telegram gateway latency, and active compression sessions.
Matches the official standard established across the Kayi Bots ecosystem.
"""
from __future__ import annotations

import html
import logging
import time
from datetime import datetime, timezone
from typing import Any

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
        process = psutil.Process()
        return process.memory_info().rss / (1024.0 * 1024.0)
    except Exception:
        return 32.0


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

    session_hours = (now - BOT_START_TIME).total_seconds() / 3600.0
    total_used_hours = min(750.0, config.render_used_hours + session_hours)
    remaining_hours = max(0.0, 750.0 - total_used_hours)
    used_pct = min(100.0, (total_used_hours / 750.0) * 100.0)
    days_left_capacity = remaining_hours / 24.0

    mem_mb = get_process_memory_mb()
    mem_pct = min(100.0, (mem_mb / 512.0) * 100.0)
    ping_ms = await measure_gateway_latency(bot)

    active_sessions = sessions.count()

    email_display = config.render_email if config.render_email else "Not Set"

    text = (
        "<b>Kayi Image Compressor — Host & Service Metrics</b>\n\n"
        "<b>Host & Cloud Account:</b>\n"
        "• <b>Cloud:</b> Render (Frankfurt, EU-Central)\n"
        f"• <b>Account Email:</b> <code>{html.escape(email_display)}</code>\n"
        f"• <b>Service Name:</b> <code>{html.escape(config.render_service_name)}</code>\n"
        f"• <b>Repository:</b> <code>{html.escape(config.render_repo)}</code>\n\n"
        "<b>Monthly Free Usage (Render Limit: 750h):</b>\n"
        f"• <b>Active Uptime:</b> <code>{uptime_str}</code>\n"
        f"• <b>Hours This Month:</b> <code>{total_used_hours:.1f}h / 750h ({used_pct:.1f}%)</code>\n"
        f"• <b>Remaining Free:</b> <code>{remaining_hours:.1f}h (~{days_left_capacity:.1f} days)</code>\n"
        f"• <b>Memory (RAM):</b> <code>{mem_mb:.1f} MB / 512 MB ({mem_pct:.1f}%)</code>\n\n"
        "<b>Compression Engine Stats:</b>\n"
        f"• <b>Active Sessions:</b> <code>{active_sessions}</code>\n"
        f"• <b>Max File Budget:</b> <code>{config.max_upload_bytes // (1024 * 1024)} MB</code>\n"
        f"• <b>Daily User Limit:</b> <code>{config.daily_user_limit} images/day</code>\n"
        f"• <b>Telegram Gateway Ping:</b> <code>{ping_ms:.1f} ms</code>"
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Refresh Metrics", callback_data="usage:refresh"
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
    # Restrict to owner if OWNER_ID is configured
    if config.owner_id and message.from_user and message.from_user.id != config.owner_id:
        return

    text, markup = await build_usage_card_text(bot, config, sessions)
    await message.answer(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)


@router.callback_query(F.data == "usage:refresh")
async def cb_usage_refresh(
    callback: CallbackQuery, bot: Bot, config: Config, sessions: SessionStore
) -> None:
    if config.owner_id and callback.from_user and callback.from_user.id != config.owner_id:
        await callback.answer("Owner only.", show_alert=True)
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
    t0 = time.perf_counter()
    ping_msg = await message.answer("🏓 <i>Pinging...</i>", parse_mode=ParseMode.HTML)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    uptime = get_uptime_string()

    text = (
        "<b>Kayi Image Compressor — Status</b>\n\n"
        f"• <b>Gateway Latency:</b> <code>{latency_ms:.1f} ms</code>\n"
        f"• <b>Uptime:</b> <code>{uptime}</code>\n"
        "• <b>Service Status:</b> <code>Operational ✅</code>"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Check Ping", callback_data="ping:refresh"
                )
            ]
        ]
    )
    await ping_msg.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)


@router.callback_query(F.data == "ping:refresh")
async def cb_ping_refresh(callback: CallbackQuery, bot: Bot) -> None:
    t0 = time.perf_counter()
    latency_ms = await measure_gateway_latency(bot)
    uptime = get_uptime_string()

    text = (
        "<b>Kayi Image Compressor — Status</b>\n\n"
        f"• <b>Gateway Latency:</b> <code>{latency_ms:.1f} ms</code>\n"
        f"• <b>Uptime:</b> <code>{uptime}</code>\n"
        "• <b>Service Status:</b> <code>Operational ✅</code>"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Check Ping", callback_data="ping:refresh"
                )
            ]
        ]
    )
    try:
        await callback.message.edit_text(
            text=text, parse_mode=ParseMode.HTML, reply_markup=markup
        )
    except Exception:
        pass
    await callback.answer()


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
                logger.debug("Could not register owner commands: %s", e)
        logger.info("Bot commands successfully registered with Telegram.")
    except Exception as e:
        logger.warning("Could not register default bot commands: %s", e)
