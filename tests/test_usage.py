"""
tests/test_usage.py

Tests for the /usage and /ping metrics commands, Render metadata,
and bot command registration.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.bot.handlers.usage import (
    mask_email,
    get_uptime_string,
    build_usage_card_text,
    cmd_usage,
    cmd_ping,
    register_bot_commands,
)
from app.config import Config
from app.services.sessions import SessionStore


def test_mask_email() -> None:
    assert mask_email("user@example.com") == "us***@example.com"
    assert mask_email("a@b.com") == "a***@b.com"
    assert mask_email("") == "[Not Configured]"
    assert mask_email("invalid") == "[Not Configured]"


def test_get_uptime_string() -> None:
    uptime = get_uptime_string()
    assert isinstance(uptime, str)
    assert len(uptime) > 0


@pytest.mark.asyncio
async def test_build_usage_card_text() -> None:
    bot = MagicMock()
    bot.get_me = AsyncMock()

    config = Config(
        bot_token="123:ABC",
        webhook_base_url="https://test.onrender.com",
        webhook_secret="secret",
        port=10000,
        bot_username="KayiImgShrinkBot",
        fsub_enabled=False,
        fsub_channel="@KayiBots",
        fsub_channel_url="https://t.me/KayiBots",
        welcome_video_file_id="",
        max_upload_bytes=8 * 1024 * 1024,
        max_image_pixels=12_000_000,
        max_queue_size=5,
        max_concurrent_jobs=1,
        processing_timeout_seconds=25,
        daily_user_limit=20,
        session_ttl_seconds=600,
        max_storage_budget_bytes=50 * 1024 * 1024,
        fsub_cache_ttl=45,
        fsub_timeout=5.0,
        log_level="INFO",
        owner_id=986380678,
        log_channel_id=0,
        render_email="giyanrtjd@gmail.com",
        render_service_name="kayi-image-compressor",
        render_repo="ZenkaiRPGBot/kayi-image-compressor",
        render_used_hours=12.5,
    )
    sessions = SessionStore()

    text, markup = await build_usage_card_text(bot, config, sessions)
    assert "Kayi Image Compressor — Host & Service Metrics" in text
    assert "giyanrtjd@gmail.com" in text
    assert "kayi-image-compressor" in text
    assert "ZenkaiRPGBot/kayi-image-compressor" in text
    assert "750h" in text
    assert len(markup.inline_keyboard) > 0


@pytest.mark.asyncio
async def test_cmd_usage_owner_restriction() -> None:
    bot = MagicMock()
    bot.get_me = AsyncMock()

    config = Config(
        bot_token="123:ABC",
        webhook_base_url="https://test.onrender.com",
        webhook_secret="secret",
        port=10000,
        bot_username="KayiImgShrinkBot",
        fsub_enabled=False,
        fsub_channel="@KayiBots",
        fsub_channel_url="https://t.me/KayiBots",
        welcome_video_file_id="",
        max_upload_bytes=8 * 1024 * 1024,
        max_image_pixels=12_000_000,
        max_queue_size=5,
        max_concurrent_jobs=1,
        processing_timeout_seconds=25,
        daily_user_limit=20,
        session_ttl_seconds=600,
        max_storage_budget_bytes=50 * 1024 * 1024,
        fsub_cache_ttl=45,
        fsub_timeout=5.0,
        log_level="INFO",
        owner_id=986380678,
        log_channel_id=0,
        render_email="test@gmail.com",
        render_service_name="kayi-image-compressor",
        render_repo="ZenkaiRPGBot/kayi-image-compressor",
        render_used_hours=0.0,
    )
    sessions = SessionStore()

    # Non-owner message
    non_owner_msg = MagicMock()
    non_owner_msg.from_user.id = 11111111
    non_owner_msg.reply = AsyncMock()
    non_owner_msg.answer = AsyncMock()

    await cmd_usage(non_owner_msg, bot, config, sessions)
    non_owner_msg.reply.assert_called_once_with("Access restricted to bot owner.")
    non_owner_msg.answer.assert_not_called()

    # Owner message
    owner_msg = MagicMock()
    owner_msg.from_user.id = 986380678
    owner_msg.answer = AsyncMock()

    await cmd_usage(owner_msg, bot, config, sessions)
    owner_msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_usage_fail_closed_when_owner_id_unset() -> None:
    from dataclasses import replace
    from app.bot.handlers.usage import cb_usage_refresh, is_owner

    bot = MagicMock()
    bot.get_me = AsyncMock()
    sessions = SessionStore()
    config = replace(
        Config(
            bot_token="123:ABC",
            webhook_base_url="https://test.onrender.com",
            webhook_secret="secret",
            port=10000,
            bot_username="KayiImgShrinkBot",
            fsub_enabled=False,
            fsub_channel="@KayiBots",
            fsub_channel_url="https://t.me/KayiBots",
            welcome_video_file_id="",
            max_upload_bytes=8 * 1024 * 1024,
            max_image_pixels=12_000_000,
            max_queue_size=5,
            max_concurrent_jobs=1,
            processing_timeout_seconds=25,
            daily_user_limit=20,
            session_ttl_seconds=600,
            max_storage_budget_bytes=50 * 1024 * 1024,
            fsub_cache_ttl=45,
            fsub_timeout=5.0,
            log_level="INFO",
            owner_id=0,
            log_channel_id=0,
            render_email="",
            render_service_name="",
            render_repo="",
            render_used_hours=0.0,
        )
    )

    assert is_owner(None, config) is False
    assert is_owner(11111111, config) is False
    assert is_owner(0, config) is False

    msg = MagicMock()
    msg.from_user.id = 11111111
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    await cmd_usage(msg, bot, config, sessions)
    msg.reply.assert_awaited_once_with("Access restricted to bot owner.")
    msg.answer.assert_not_called()

    cb = MagicMock()
    cb.from_user.id = 11111111
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    await cb_usage_refresh(cb, bot, config, sessions)
    cb.answer.assert_awaited_once_with("Access restricted to bot owner.", show_alert=True)
    cb.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_ping() -> None:
    bot = MagicMock()
    bot.get_me = AsyncMock()

    msg = MagicMock()
    msg.reply = AsyncMock()

    await cmd_ping(msg, bot)
    msg.reply.assert_called_once()
    call_kwargs = msg.reply.call_args[1]
    assert "Pong!" in call_kwargs["text"]
    assert "Bot Responsiveness" in call_kwargs["text"]
    assert "Telegram API Latency" in call_kwargs["text"]
    assert call_kwargs["reply_markup"].inline_keyboard[0][0].model_dump(exclude_none=True)["style"] == "primary"


@pytest.mark.asyncio
async def test_register_bot_commands() -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()

    config = Config(
        bot_token="123:ABC",
        webhook_base_url="https://test.onrender.com",
        webhook_secret="secret",
        port=10000,
        bot_username="KayiImgShrinkBot",
        fsub_enabled=False,
        fsub_channel="@KayiBots",
        fsub_channel_url="https://t.me/KayiBots",
        welcome_video_file_id="",
        max_upload_bytes=8 * 1024 * 1024,
        max_image_pixels=12_000_000,
        max_queue_size=5,
        max_concurrent_jobs=1,
        processing_timeout_seconds=25,
        daily_user_limit=20,
        session_ttl_seconds=600,
        max_storage_budget_bytes=50 * 1024 * 1024,
        fsub_cache_ttl=45,
        fsub_timeout=5.0,
        log_level="INFO",
        owner_id=986380678,
        log_channel_id=0,
        render_email="",
        render_service_name="",
        render_repo="",
        render_used_hours=0.0,
    )

    await register_bot_commands(bot, config)
    # Called twice: once for default scope, once for owner chat scope
    assert bot.set_my_commands.call_count == 2
