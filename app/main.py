"""
app/main.py

Kayi Image Compressor — Application entry point.

Startup sequence:
  1. Load and validate configuration
  2. Clean up orphaned temp files
  3. Create Bot + Dispatcher
  4. Register middlewares and handlers
  5. Register Telegram webhook
  6. Start aiohttp server
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path so 'import app...' works regardless of invocation method
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from app.config import load_config
from app.services.cleanup import cleanup_orphaned_files
from app.services.restart_notify import build_restart_notifier
from app.services.sessions import SessionStore
from app.services.rate_limits import RateLimiter
from app.services.queue import JobQueue
from app.bot.middlewares.fsub import FSubMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.handlers import start, help, compress, callbacks, usage
from app.bot.handlers.usage import register_bot_commands
from app.web.webhook import build_webhook_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    # ── 1. Configuration ───────────────────────────────────────────────────
    config = load_config()
    logging.getLogger().setLevel(config.log_level)
    logger.info("Starting Kayi Image Compressor (port=%d, fsub=%s)", config.port, config.fsub_enabled)

    # ── 2. Startup cleanup ─────────────────────────────────────────────────
    cleanup_orphaned_files(max_age_seconds=3600)

    # ── 3. Services ────────────────────────────────────────────────────────
    sessions = SessionStore(ttl_seconds=config.session_ttl_seconds)
    rate_limiter = RateLimiter(
        daily_limit=config.daily_user_limit,
        cooldown_seconds=3.0,
    )

    # ── 4. Bot + Dispatcher ────────────────────────────────────────────────
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # ── 5. Inject dependencies into handler data ───────────────────────────
    dp["config"] = config
    dp["sessions"] = sessions
    dp["rate_limiter"] = rate_limiter

    # ── 6. Middlewares ─────────────────────────────────────────────────────
    dp.message.middleware(FSubMiddleware(config))
    dp.callback_query.middleware(FSubMiddleware(config))
    dp.message.middleware(RateLimitMiddleware(rate_limiter))

    # ── 7. Routers ─────────────────────────────────────────────────────────
    dp.include_router(start.router)
    dp.include_router(help.router)
    dp.include_router(usage.router)
    dp.include_router(callbacks.router)  # callbacks before compress to avoid message routing conflicts
    dp.include_router(compress.router)

    # ── 8. Register webhook & commands ────────────────────────────────────
    webhook_url = config.webhook_url
    logger.info("Registering webhook: %s", webhook_url)
    await bot.set_webhook(
        url=webhook_url,
        secret_token=config.webhook_secret or None,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )
    await register_bot_commands(bot, config)

    # Confirm registration
    wh_info = await bot.get_webhook_info()
    logger.info(
        "Webhook registered: url=%s pending=%d",
        wh_info.url,
        wh_info.pending_update_count,
    )

    # ── 9. Build aiohttp app ───────────────────────────────────────────────
    app = build_webhook_app(bot, dp, webhook_secret=config.webhook_secret)

    # ── 10. Session cleanup task ───────────────────────────────────────────
    async def session_cleanup_task() -> None:
        while True:
            await asyncio.sleep(300)
            removed = sessions.cleanup()
            if removed:
                logger.debug("Session cleanup: removed %d expired sessions.", removed)

    # ── 11. Start server ───────────────────────────────────────────────────
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.port)
    await site.start()

    cleanup_task = asyncio.create_task(session_cleanup_task())
    restart_task = asyncio.create_task(build_restart_notifier(bot, config).notify_once())
    logger.info("Server running on port %d. Ready.", config.port)

    try:
        await asyncio.Event().wait()  # Run forever
    finally:
        cleanup_task.cancel()
        restart_task.cancel()
        await bot.delete_webhook()
        await bot.session.close()
        await runner.cleanup()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
