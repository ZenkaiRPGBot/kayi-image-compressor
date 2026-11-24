"""
app/web/health.py

Simple health check endpoint. Does not expose secrets.
"""
from __future__ import annotations

import time

from aiohttp import web

_start_time = time.time()


async def health_handler(request: web.Request) -> web.Response:
    uptime_seconds = int(time.time() - _start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return web.json_response({
        "status": "ok",
        "service": "kayi-image-compressor",
        "uptime": uptime_str,
    })
