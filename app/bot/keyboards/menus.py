"""
app/bot/keyboards/menus.py

All keyboard builder functions for Kayi Image Compressor.
Matches the official visual standards and button styling of the Kayi Bots ecosystem.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_welcome_keyboard(
    channel_url: str = "https://t.me/KayiBots",
    developer_url: str = "https://t.me/qouba",
) -> InlineKeyboardMarkup:
    """Builds the official /start keyboard without redundant Help buttons."""
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
    """Main compression choices for an uploaded image."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Auto Optimize", callback_data=f"comp:auto:{session_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="🎯 Target Size", callback_data=f"comp:menu_target:{session_id}"),
            InlineKeyboardButton(text="📋 Form Upload Mode", callback_data=f"comp:menu_form:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="🎚 Quality Presets", callback_data=f"comp:menu_presets:{session_id}"),
            InlineKeyboardButton(text="🎨 Specialized Modes", callback_data=f"comp:menu_spec:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Advanced Controls", callback_data=f"comp:menu_adv:{session_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"comp:cancel:{session_id}", style="danger"),
        ]
    ])


def build_target_size_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Target size presets strictly matching Row 1: 20|50|100, Row 2: 200|500|1MB."""
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


def build_quality_presets_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Quality preset options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Best Quality", callback_data=f"comp:preset:best_quality:{session_id}"),
            InlineKeyboardButton(text="⚖️ Balanced", callback_data=f"comp:preset:balanced:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="📦 Smallest File", callback_data=f"comp:preset:smallest:{session_id}"),
            InlineKeyboardButton(text="💎 Lossless", callback_data=f"comp:preset:lossless:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}"),
        ]
    ])


def build_specialized_presets_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Specialized modes for photos, text, signatures, forms, and transparent files."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📸 Photo Mode", callback_data=f"comp:preset:photo:{session_id}"),
            InlineKeyboardButton(text="🖥️ Screenshot & Text", callback_data=f"comp:preset:screenshot:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="✍️ Signature Mode", callback_data=f"comp:preset:signature:{session_id}"),
            InlineKeyboardButton(text="🪪 Form Photo Mode", callback_data=f"comp:preset:form_photo:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="✨ Transparent Mode", callback_data=f"comp:preset:transparent:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}"),
        ]
    ])


def build_form_upload_keyboard(session_id: str, stage: str = "size") -> InlineKeyboardMarkup:
    """Guided workflow for portal form upload constraints."""
    if stage == "size":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Max 20 KB", callback_data=f"form:size:20:{session_id}"),
                InlineKeyboardButton(text="Max 50 KB", callback_data=f"form:size:50:{session_id}"),
                InlineKeyboardButton(text="Max 100 KB", callback_data=f"form:size:100:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="Max 200 KB", callback_data=f"form:size:200:{session_id}"),
                InlineKeyboardButton(text="Max 500 KB", callback_data=f"form:size:500:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="Custom Size…", callback_data=f"form:size:custom:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}"),
            ]
        ])

    elif stage == "format":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="JPEG / JPG", callback_data=f"form:fmt:JPEG:{session_id}"),
                InlineKeyboardButton(text="PNG", callback_data=f"form:fmt:PNG:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="WebP", callback_data=f"form:fmt:WEBP:{session_id}"),
                InlineKeyboardButton(text="Keep Original", callback_data=f"form:fmt:KEEP:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="‹ Back", callback_data=f"comp:menu_form:{session_id}"),
            ]
        ])

    elif stage == "fit":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Keep Aspect Ratio", callback_data=f"form:fit:fit:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="Square 1:1 (Pad White)", callback_data=f"form:fit:pad_sq:{session_id}"),
                InlineKeyboardButton(text="Square 1:1 (Crop)", callback_data=f"form:fit:crop_sq:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="Passport 3:4 (Pad)", callback_data=f"form:fit:pad_pass:{session_id}"),
                InlineKeyboardButton(text="Passport 3:4 (Crop)", callback_data=f"form:fit:crop_pass:{session_id}"),
            ],
            [
                InlineKeyboardButton(text="‹ Back", callback_data=f"comp:menu_form:{session_id}"),
            ]
        ])

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}")]
    ])


def build_advanced_controls_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Advanced controls: percentage scaling, dimensions, and metadata."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Scale 75%", callback_data=f"adv:scale:75:{session_id}"),
            InlineKeyboardButton(text="Scale 50%", callback_data=f"adv:scale:50:{session_id}"),
            InlineKeyboardButton(text="Scale 25%", callback_data=f"adv:scale:25:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="Format: to JPEG", callback_data=f"adv:fmt:JPEG:{session_id}"),
            InlineKeyboardButton(text="Format: to PNG", callback_data=f"adv:fmt:PNG:{session_id}"),
            InlineKeyboardButton(text="Format: to WebP", callback_data=f"adv:fmt:WEBP:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="Preserve EXIF", callback_data=f"adv:meta:keep:{session_id}"),
            InlineKeyboardButton(text="Strip EXIF (Default)", callback_data=f"adv:meta:strip:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="‹ Back", callback_data=f"comp:back_main:{session_id}"),
        ]
    ])


def build_result_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Result action buttons: 1-tap retries, setting change, and compress another."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📉 Smaller Size", callback_data=f"retry:smaller:{session_id}"),
            InlineKeyboardButton(text="📈 Better Quality", callback_data=f"retry:better:{session_id}"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Change Settings", callback_data=f"retry:settings:{session_id}"),
            InlineKeyboardButton(text="🗜 Compress Another", callback_data="compress:start", style="success"),
        ]
    ])
