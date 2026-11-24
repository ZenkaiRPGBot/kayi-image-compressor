"""
app/config.py — Kayi Image Compressor configuration.

All settings are loaded from environment variables at startup.
Missing required variables raise an error immediately.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.example to .env and fill in all required values."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class Config:
    # Required
    bot_token: str
    webhook_base_url: str

    # Optional
    webhook_secret: str
    port: int
    bot_username: str

    # FSub
    fsub_enabled: bool
    fsub_channel: str
    fsub_channel_url: str

    # Branding
    welcome_video_file_id: str

    # Limits
    max_upload_bytes: int
    max_image_pixels: int
    max_queue_size: int
    max_concurrent_jobs: int
    processing_timeout_seconds: int
    daily_user_limit: int
    session_ttl_seconds: int
    max_storage_budget_bytes: int
    fsub_cache_ttl: int
    fsub_timeout: float

    # Logging
    log_level: str
    owner_id: int
    log_channel_id: int

    # Render Cloud Hosting Metadata
    render_email: str
    render_service_name: str
    render_repo: str
    render_used_hours: float

    @property
    def webhook_url(self) -> str:
        base = self.webhook_base_url.rstrip("/")
        return f"{base}/webhook"


def load_config() -> Config:
    bot_token = _require("BOT_TOKEN")
    webhook_base_url = _require("WEBHOOK_BASE_URL")

    max_upload_mb = _int("MAX_UPLOAD_MB", 8)

    owner_id_str = _optional("OWNER_ID", "0")
    log_channel_id_str = _optional("LOG_CHANNEL_ID", "0")

    try:
        owner_id = int(owner_id_str) if owner_id_str else 0
    except ValueError:
        owner_id = 0

    try:
        log_channel_id = int(log_channel_id_str) if log_channel_id_str else 0
    except ValueError:
        log_channel_id = 0

    max_storage_mb = _int("MAX_STORAGE_MB", 50)

    webhook_secret = _optional("WEBHOOK_SECRET")
    is_prod = _bool("IS_PRODUCTION", False) or "onrender.com" in webhook_base_url
    if is_prod and not webhook_secret:
        # In production Render deployments, WEBHOOK_SECRET is required
        raise EnvironmentError(
            "WEBHOOK_SECRET is required in production deployment (Render). "
            "Please configure WEBHOOK_SECRET in your environment."
        )

    render_email = _optional("RENDER_EMAIL", "")
    render_service_name = _optional("RENDER_SERVICE_NAME", "kayi-image-compressor")
    render_repo = _optional("RENDER_REPO", "ZenkaiRPGBot/kayi-image-compressor")
    try:
        render_used_hours = float(_optional("RENDER_USED_HOURS", "0.0"))
    except ValueError:
        render_used_hours = 0.0

    return Config(
        bot_token=bot_token,
        webhook_base_url=webhook_base_url,
        webhook_secret=webhook_secret,
        port=_int("PORT", 10000),
        bot_username=_optional("BOT_USERNAME", "KayiImgShrinkBot"),
        fsub_enabled=_bool("FSUB_ENABLED", False),
        fsub_channel=_optional("FSUB_CHANNEL", "@KayiBots"),
        fsub_channel_url=_optional("FSUB_CHANNEL_URL", "https://t.me/KayiBots"),
        welcome_video_file_id=_optional("WELCOME_VIDEO_FILE_ID"),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        max_image_pixels=_int("MAX_IMAGE_PIXELS", 12_000_000),
        max_queue_size=_int("MAX_QUEUE_SIZE", 5),
        max_concurrent_jobs=_int("MAX_CONCURRENT_JOBS", 1),
        processing_timeout_seconds=_int("PROCESSING_TIMEOUT_SECONDS", 25),
        daily_user_limit=_int("DAILY_USER_LIMIT", 20),
        session_ttl_seconds=_int("SESSION_TTL_SECONDS", 600),
        max_storage_budget_bytes=max_storage_mb * 1024 * 1024,
        fsub_cache_ttl=_int("FSUB_CACHE_TTL", 45),
        fsub_timeout=float(os.environ.get("FSUB_TIMEOUT", "5.0")),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
        owner_id=owner_id,
        log_channel_id=log_channel_id,
        render_email=render_email,
        render_service_name=render_service_name,
        render_repo=render_repo,
        render_used_hours=render_used_hours,
    )
