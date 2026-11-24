"""
app/bot/keyboards/menus.py

Simplified, elegant keyboard builders for Kayi Image Compressor.
Matches the official visual standards and button styling of the Kayi Bots ecosystem.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

if TYPE_CHECKING:
    from app.services.sessions import UserSession


def build_welcome_keyboard(
    channel_url: str = "https://t.me/KayiBots",
    developer_url: str = "https://t.me/qouba",
) -> InlineKeyboardMarkup:
    """Builds the official /start keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗜 Compress an Image", callback_data="compress:start", style="success")
        ],
        [
            InlineKeyboardButton(text="📢 Updates", url=channel_url),
            InlineKeyboardButton(text="👨‍💻 Developer", url=developer_url),
        ]
    ])


def build_help_keyboard(developer_url: str = "https://t.me/qouba") -> InlineKeyboardMarkup:
    """Builds clean, flat Help keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨‍💻 Developer", url=developer_url)
        ]
    ])


def build_image_options_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """
    Primary post-upload compression options:
    - Auto Compress
    - Set Target Size
    - Advanced Settings
    - Cancel
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Auto Compress", callback_data=f"comp:auto:{session_id}")
        ],
        [
            InlineKeyboardButton(text="🎯 Set Target Size", callback_data=f"comp:menu_target:{session_id}")
        ],
        [
            InlineKeyboardButton(text="⚙️ Advanced Settings", callback_data=f"comp:menu_adv:{session_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"comp:cancel:{session_id}")
        ]
    ])


def build_target_size_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """
    Target size presets:
    Row 1: 20 KB | 50 KB | 100 KB
    Row 2: 200 KB | 500 KB | 1 MB
    Row 3: Custom Size
    Row 4: Back
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="20 KB", callback_data=f"comp:target:20:{session_id}"),
            InlineKeyboardButton(text="50 KB", callback_data=f"comp:target:50:{session_id}"),
            InlineKeyboardButton(text="100 KB", callback_data=f"comp:target:100:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="200 KB", callback_data=f"comp:target:200:{session_id}"),
            InlineKeyboardButton(text="500 KB", callback_data=f"comp:target:500:{session_id}"),
            InlineKeyboardButton(text="1 MB", callback_data=f"comp:target:1024:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Custom Size", callback_data=f"comp:target:custom:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}"),
        ]
    ])


def build_advanced_settings_keyboard(session: "UserSession") -> InlineKeyboardMarkup:
    """
    Advanced Settings dashboard:
    Quality preset, output format, dimension downscaling, and metadata stripping.
    Applies consistently to both Auto Compress and Target Size.
    """
    sid = session.session_id
    p = session.selected_preset
    f = session.selected_format
    s = session.scale_percent
    m = session.strip_metadata

    def mark(cond: bool, text: str) -> str:
        return f"✓ {text}" if cond else text

    return InlineKeyboardMarkup(inline_keyboard=[
        # Row 1: Quality Preset
        [
            InlineKeyboardButton(text=mark(p == "best_quality", "⭐ Best"), callback_data=f"adv:preset:best_quality:{sid}"),
            InlineKeyboardButton(text=mark(p == "balanced", "⚖️ Balanced"), callback_data=f"adv:preset:balanced:{sid}"),
            InlineKeyboardButton(text=mark(p == "smallest", "📦 Smallest"), callback_data=f"adv:preset:smallest:{sid}"),
            InlineKeyboardButton(text=mark(p == "lossless", "💎 Lossless"), callback_data=f"adv:preset:lossless:{sid}"),
        ],
        # Row 2: Format Selection
        [
            InlineKeyboardButton(text=mark(f == "", "Original"), callback_data=f"adv:fmt:ORIGINAL:{sid}"),
            InlineKeyboardButton(text=mark(f == "JPEG", "JPEG"), callback_data=f"adv:fmt:JPEG:{sid}"),
            InlineKeyboardButton(text=mark(f == "PNG", "PNG"), callback_data=f"adv:fmt:PNG:{sid}"),
            InlineKeyboardButton(text=mark(f == "WEBP", "WebP"), callback_data=f"adv:fmt:WEBP:{sid}"),
        ],
        # Row 3: Scaling
        [
            InlineKeyboardButton(text=mark(s >= 0.99, "100%"), callback_data=f"adv:scale:100:{sid}"),
            InlineKeyboardButton(text=mark(0.70 <= s <= 0.80, "75%"), callback_data=f"adv:scale:75:{sid}"),
            InlineKeyboardButton(text=mark(0.45 <= s <= 0.55, "50%"), callback_data=f"adv:scale:50:{sid}"),
            InlineKeyboardButton(text=mark(0.20 <= s <= 0.30, "25%"), callback_data=f"adv:scale:25:{sid}"),
        ],
        # Row 4: Metadata
        [
            InlineKeyboardButton(text=mark(m, "Strip EXIF"), callback_data=f"adv:meta:strip:{sid}"),
            InlineKeyboardButton(text=mark(not m, "Preserve EXIF"), callback_data=f"adv:meta:keep:{sid}"),
        ],
        # Row 5: Back
        [
            InlineKeyboardButton(text="‹ Back to Options", callback_data=f"comp:back_main:{sid}"),
        ]
    ])


def build_result_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Result action buttons: 1-tap retries, advanced settings, and compress another."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📉 Smaller Size", callback_data=f"retry:smaller:{session_id}"),
            InlineKeyboardButton(text="📈 Better Quality", callback_data=f"retry:better:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Advanced Settings", callback_data=f"comp:menu_adv:{session_id}"),
            InlineKeyboardButton(text="🗜 Compress Another", callback_data="compress:start", style="success"),
        ]
    ])
