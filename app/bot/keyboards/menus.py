"""
app/bot/keyboards/menus.py

Native colored inline keyboard builders for Kayi Image Compressor.
Follows the official Telegram Bot API `style` property ("primary", "success", "danger")
and the Kayi Bots ecosystem visual design system.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

if TYPE_CHECKING:
    from app.services.sessions import UserSession


def _opt_btn(selected: bool, label: str, callback_data: str) -> InlineKeyboardButton:
    """Helper for dynamic selection highlighting in Advanced Settings."""
    if selected:
        return InlineKeyboardButton(
            text=f"✓ {label}",
            callback_data=callback_data,
            style="primary",
        )
    return InlineKeyboardButton(
        text=label,
        callback_data=callback_data,
    )


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
            InlineKeyboardButton(text="📢 Updates", url=channel_url, style="primary"),
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


def build_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Builds a clean single-button Back navigation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="‹ Back", callback_data=callback_data)
        ]
    ])


def build_image_options_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """
    Primary post-upload menu:
    Row 1: Auto Compress — success
    Row 2: Set Target Size — primary
    Row 3: Advanced Settings — primary
    Row 4: Cancel — danger
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Auto Compress", callback_data=f"comp:auto:{session_id}", style="success")
        ],
        [
            InlineKeyboardButton(text="🎯 Set Target Size", callback_data=f"comp:menu_target:{session_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="⚙️ Advanced Settings", callback_data=f"comp:menu_adv:{session_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="Cancel", callback_data=f"comp:cancel:{session_id}", style="danger")
        ]
    ])


def build_target_size_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """
    Target size presets:
    Row 1: 20 KB | 50 KB | 100 KB — success
    Row 2: 200 KB | 500 KB | 1 MB — success
    Row 3: Custom Size — primary
    Row 4: Back — default
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="20 KB", callback_data=f"comp:target:20:{session_id}", style="success"),
            InlineKeyboardButton(text="50 KB", callback_data=f"comp:target:50:{session_id}", style="success"),
            InlineKeyboardButton(text="100 KB", callback_data=f"comp:target:100:{session_id}", style="success"),
        ],
        [
            InlineKeyboardButton(text="200 KB", callback_data=f"comp:target:200:{session_id}", style="success"),
            InlineKeyboardButton(text="500 KB", callback_data=f"comp:target:500:{session_id}", style="success"),
            InlineKeyboardButton(text="1 MB", callback_data=f"comp:target:1024:{session_id}", style="success"),
        ],
        [
            InlineKeyboardButton(text="✏️ Custom Size", callback_data=f"comp:target:custom:{session_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}"),
        ]
    ])


def build_advanced_settings_keyboard(session: "UserSession") -> InlineKeyboardMarkup:
    """
    Advanced Settings dashboard with dynamic selection highlighting.
    Selected: style="primary" + "✓ " prefix.
    Unselected: default style, no checkmark.
    Two buttons per row for mobile clarity.
    """
    sid = session.session_id
    p = session.selected_preset
    f = session.selected_format
    d = session.dimension_mode
    m = session.strip_metadata

    return InlineKeyboardMarkup(inline_keyboard=[
        # Quality
        [
            _opt_btn(p == "best_quality", "Best", f"adv:preset:best_quality:{sid}"),
            _opt_btn(p == "balanced", "Balanced", f"adv:preset:balanced:{sid}"),
        ],
        [
            _opt_btn(p == "smallest", "Smallest", f"adv:preset:smallest:{sid}"),
            _opt_btn(p == "lossless", "Lossless", f"adv:preset:lossless:{sid}"),
        ],
        # Format
        [
            _opt_btn(f == "", "Original", f"adv:fmt:ORIGINAL:{sid}"),
            _opt_btn(f == "JPEG", "JPEG", f"adv:fmt:JPEG:{sid}"),
        ],
        [
            _opt_btn(f == "PNG", "PNG", f"adv:fmt:PNG:{sid}"),
            _opt_btn(f == "WEBP", "WebP", f"adv:fmt:WEBP:{sid}"),
        ],
        # Dimensions
        [
            _opt_btn(d == "auto", "Automatic", f"adv:dim:auto:{sid}"),
            _opt_btn(d == "100", "100%", f"adv:dim:100:{sid}"),
        ],
        [
            _opt_btn(d == "75", "75%", f"adv:dim:75:{sid}"),
            _opt_btn(d == "50", "50%", f"adv:dim:50:{sid}"),
        ],
        [
            _opt_btn(d == "25", "25%", f"adv:dim:25:{sid}"),
            _opt_btn(d == "custom", "Custom", f"adv:dim:custom:{sid}"),
        ],
        # Metadata
        [
            _opt_btn(m, "Remove", f"adv:meta:strip:{sid}"),
            _opt_btn(not m, "Preserve", f"adv:meta:keep:{sid}"),
        ],
        # Actions
        [
            InlineKeyboardButton(text="Apply Settings", callback_data=f"adv:apply:{sid}", style="success"),
        ],
        [
            InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{sid}"),
        ]
    ])


def build_result_keyboard(session_id: str, success: bool = True) -> InlineKeyboardMarkup:
    """
    Result action buttons:
    - If success: Smaller Size / Better Quality (primary), Change Settings (default), Compress Another (success)
    - If unsuccessful: Retry actions in primary style, no green success styling
    """
    if not success:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📉 Try Smaller Target", callback_data=f"retry:smaller:{session_id}", style="primary"),
                InlineKeyboardButton(text="⚙️ Change Settings", callback_data=f"comp:menu_adv:{session_id}", style="primary"),
            ],
            [
                InlineKeyboardButton(text="🗜 Compress Another", callback_data="compress:start"),
            ]
        ])

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📉 Smaller Size", callback_data=f"retry:smaller:{session_id}", style="primary"),
            InlineKeyboardButton(text="📈 Better Quality", callback_data=f"retry:better:{session_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Change Settings", callback_data=f"comp:menu_adv:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="🗜 Compress Another", callback_data="compress:start", style="success"),
        ]
    ])
