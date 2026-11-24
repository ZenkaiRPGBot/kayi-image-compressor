"""
tests/test_webhook_security.py

Tests for webhook security, header secret verification, and health check.
Uses native aiohttp TestServer and TestClient.
"""
import pytest
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot, Dispatcher

from app.web.webhook import build_webhook_app


@pytest.mark.asyncio
async def test_webhook_secret_header_enforcement():
    mock_bot = MagicMock(spec=Bot)
    mock_dp = MagicMock(spec=Dispatcher)
    mock_dp.feed_update = AsyncMock()

    secret = "test_super_secret_token_123"
    app = build_webhook_app(mock_bot, mock_dp, webhook_secret=secret)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # 1. Missing secret header -> 403 Forbidden
        resp = await client.post("/webhook", json={"update_id": 1})
        assert resp.status == 403

        # 2. Invalid secret header -> 403 Forbidden
        resp = await client.post(
            "/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_token"},
        )
        assert resp.status == 403

        # 3. Valid secret header -> 200 OK
        resp = await client.post(
            "/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": secret},
        )
        assert resp.status == 200
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_health_endpoint_no_secrets():
    mock_bot = MagicMock(spec=Bot)
    mock_dp = MagicMock(spec=Dispatcher)

    app = build_webhook_app(mock_bot, mock_dp, webhook_secret="secret123")
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "kayi-image-compressor"
        assert "secret123" not in str(data)
    finally:
        await client.close()
