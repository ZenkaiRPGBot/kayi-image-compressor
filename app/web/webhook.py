"""
app/web/webhook.py

aiohttp webhook handler for Telegram updates.
Validates the X-Telegram-Bot-Api-Secret-Token header when WEBHOOK_SECRET is set.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update

logger = logging.getLogger(__name__)


def build_webhook_app(bot: Bot, dp: Dispatcher, webhook_secret: str = "") -> web.Application:
    """
    Build and return an aiohttp Application with:
      POST /webhook  — Telegram update handler
      GET  /health   — Health check
    """
    from app.web.health import health_handler

    async def webhook_handler(request: web.Request) -> web.Response:
        # Validate secret token header
        if webhook_secret:
            token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(token_header, webhook_secret):
                logger.warning("Invalid webhook secret token from %s", request.remote)
                return web.Response(status=403, text="Forbidden")

        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="Bad Request")

        try:
            update = Update.model_validate(data)
            await dp.feed_update(bot, update)
        except Exception as e:
            logger.exception("Error processing update: %s", e)

        return web.Response(status=200, text="ok")

    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/health", health_handler)
    return app
