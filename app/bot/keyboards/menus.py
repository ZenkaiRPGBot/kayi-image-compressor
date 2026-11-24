"""
app/bot/keyboards/menus.py

All keyboard builder functions for Kayi Image Compressor.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_start_keyboard(channel_url: str = "https://t.me/KayiBots") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗜 Compress an Image", callback_data="compress:start"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Settings", callback_data="settings:open"),
        InlineKeyboardButton(text="ℹ️ Help", callback_data="help:main"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Updates", url=channel_url),
        InlineKeyboardButton(text="👤 Developer", url="https://t.me/qouba"),
    )
    return builder.as_markup()


def build_fsub_keyboard(channel_url: str, channel_name: str = "@KayiBots") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"📢 Join {channel_name}", url=channel_url),
    )
    builder.row(
        InlineKeyboardButton(text="✅ I've Joined", callback_data="fsub:check"),
    )
    return builder.as_markup()


def build_image_options_keyboard(session_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚡ Auto Optimize", callback_data=f"compress:auto:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🎚 Quality Presets", callback_data=f"compress:presets:{session_id}"),
        InlineKeyboardButton(text="📏 Target Size", callback_data=f"compress:target_menu:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"compress:cancel:{session_id}"),
    )
    return builder.as_markup()


def build_quality_presets_keyboard(session_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⭐ Best Quality", callback_data=f"compress:preset:best_quality:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⚖️ Balanced", callback_data=f"compress:preset:balanced:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📦 Smallest File", callback_data=f"compress:preset:smallest:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="💎 Lossless", callback_data=f"compress:preset:lossless:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="‹ Back", callback_data=f"compress:back_options:{session_id}"),
    )
    return builder.as_markup()


def build_target_size_keyboard(session_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="100 KB", callback_data=f"compress:target:100:{session_id}"),
        InlineKeyboardButton(text="200 KB", callback_data=f"compress:target:200:{session_id}"),
        InlineKeyboardButton(text="500 KB", callback_data=f"compress:target:500:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="1 MB", callback_data=f"compress:target:1024:{session_id}"),
        InlineKeyboardButton(text="2 MB", callback_data=f"compress:target:2048:{session_id}"),
        InlineKeyboardButton(text="Custom…", callback_data=f"compress:target:custom:{session_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="‹ Back", callback_data=f"compress:back_options:{session_id}"),
    )
    return builder.as_markup()


def build_result_keyboard(session_id: str, channel_url: str = "https://t.me/KayiBots") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗜 Compress Another", callback_data="compress:another"),
        InlineKeyboardButton(text="📢 Updates", url=channel_url),
    )
    return builder.as_markup()


def build_help_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔒 Privacy Policy", callback_data="help:privacy"),
    )
    builder.row(
        InlineKeyboardButton(text="‹ Back to Start", callback_data="help:back"),
    )
    return builder.as_markup()


def build_help_privacy_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="‹ Back to Help", callback_data="help:main"),
    )
    return builder.as_markup()


def build_back_to_start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="‹ Back", callback_data="help:back"),
    )
    return builder.as_markup()
