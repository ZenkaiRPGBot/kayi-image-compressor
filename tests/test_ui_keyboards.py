"""
tests/test_ui_keyboards.py

Verifies native Telegram inline button colors (style="primary", "success", "danger"),
dynamic selection highlighting in Advanced Settings, result keyboard failure safety,
and JSON serialization into Telegram API requests.
"""
from __future__ import annotations

import json

from app.bot.keyboards.menus import (
    build_welcome_keyboard,
    build_help_keyboard,
    build_image_options_keyboard,
    build_target_size_keyboard,
    build_advanced_settings_keyboard,
    build_result_keyboard,
)
from app.bot.middlewares.fsub import build_fsub_keyboard
from app.services.sessions import UserSession


def _style(btn) -> str | None:
    d = btn.model_dump(exclude_none=True)
    return d.get("style")


def test_post_upload_menu_colors() -> None:
    kb = build_image_options_keyboard("sess1")
    rows = kb.inline_keyboard
    assert len(rows) == 4
    assert rows[0][0].text == "⚡ Auto Compress" and _style(rows[0][0]) == "success"
    assert rows[1][0].text == "🎯 Set Target Size" and _style(rows[1][0]) == "primary"
    assert rows[2][0].text == "⚙️ Advanced Settings" and _style(rows[2][0]) == "primary"
    assert rows[3][0].text == "Cancel" and _style(rows[3][0]) == "danger"


def test_target_size_menu_colors() -> None:
    kb = build_target_size_keyboard("sess1")
    rows = kb.inline_keyboard
    assert len(rows) == 4
    # Row 1 & 2: all 6 presets are success
    for r in (0, 1):
        assert len(rows[r]) == 3
        for btn in rows[r]:
            assert _style(btn) == "success"
    # Row 3: Custom Size -> primary
    assert _style(rows[2][0]) == "primary"
    # Row 4: Back -> default (None)
    assert _style(rows[3][0]) is None


def test_advanced_settings_dynamic_selection() -> None:
    session = UserSession(session_id="sess1", user_id=123)
    # Default: balanced, Original (""), auto, strip_metadata=True
    kb = build_advanced_settings_keyboard(session)
    flat = [b for row in kb.inline_keyboard for b in row]
    by_cb = {b.callback_data: b for b in flat}

    # Selected
    assert by_cb["adv:preset:balanced:sess1"].text == "✓ Balanced"
    assert _style(by_cb["adv:preset:balanced:sess1"]) == "primary"
    assert by_cb["adv:fmt:ORIGINAL:sess1"].text == "✓ Original"
    assert _style(by_cb["adv:fmt:ORIGINAL:sess1"]) == "primary"
    assert by_cb["adv:dim:auto:sess1"].text == "✓ Automatic"
    assert _style(by_cb["adv:dim:auto:sess1"]) == "primary"
    assert by_cb["adv:meta:strip:sess1"].text == "✓ Remove"
    assert _style(by_cb["adv:meta:strip:sess1"]) == "primary"

    # Unselected
    assert by_cb["adv:preset:best_quality:sess1"].text == "Best"
    assert _style(by_cb["adv:preset:best_quality:sess1"]) is None
    assert by_cb["adv:fmt:PNG:sess1"].text == "PNG"
    assert _style(by_cb["adv:fmt:PNG:sess1"]) is None

    # Change selection -> verify immediate update
    session.selected_preset = "lossless"
    session.selected_format = "PNG"
    session.dimension_mode = "75"
    session.strip_metadata = False

    kb2 = build_advanced_settings_keyboard(session)
    by_cb2 = {b.callback_data: b for row in kb2.inline_keyboard for b in row}

    assert by_cb2["adv:preset:lossless:sess1"].text == "✓ Lossless"
    assert _style(by_cb2["adv:preset:lossless:sess1"]) == "primary"
    assert by_cb2["adv:preset:balanced:sess1"].text == "Balanced"
    assert _style(by_cb2["adv:preset:balanced:sess1"]) is None
    assert by_cb2["adv:fmt:PNG:sess1"].text == "✓ PNG"
    assert _style(by_cb2["adv:fmt:PNG:sess1"]) == "primary"
    assert by_cb2["adv:dim:75:sess1"].text == "✓ 75%"
    assert _style(by_cb2["adv:dim:75:sess1"]) == "primary"
    assert by_cb2["adv:meta:keep:sess1"].text == "✓ Preserve"
    assert _style(by_cb2["adv:meta:keep:sess1"]) == "primary"

    # Apply & Back
    assert _style(by_cb2["adv:apply:sess1"]) == "success"
    assert _style(by_cb2["comp:back_main:sess1"]) is None


def test_result_keyboard_success_vs_failure() -> None:
    kb_ok = build_result_keyboard("sess1", success=True)
    ok_btns = [b for row in kb_ok.inline_keyboard for b in row]
    ok_by_cb = {b.callback_data: b for b in ok_btns}
    assert _style(ok_by_cb["retry:smaller:sess1"]) == "primary"
    assert _style(ok_by_cb["retry:better:sess1"]) == "primary"
    assert _style(ok_by_cb["comp:menu_adv:sess1"]) is None
    assert _style(ok_by_cb["compress:start"]) == "success"

    kb_fail = build_result_keyboard("sess1", success=False)
    fail_btns = [b for row in kb_fail.inline_keyboard for b in row]
    # No green success button on failure
    assert all(_style(b) != "success" for b in fail_btns)
    assert any(_style(b) == "primary" for b in fail_btns)


def test_fsub_and_welcome_colors() -> None:
    fsub = build_fsub_keyboard("https://t.me/KayiBots", "@KayiBots")
    assert _style(fsub.inline_keyboard[0][0]) == "primary"
    assert _style(fsub.inline_keyboard[1][0]) == "success"

    welcome = build_welcome_keyboard()
    assert _style(welcome.inline_keyboard[0][0]) == "success"
    assert _style(welcome.inline_keyboard[1][0]) == "primary"
    assert _style(welcome.inline_keyboard[1][1]) is None

    help_kb = build_help_keyboard()
    assert _style(help_kb.inline_keyboard[0][0]) is None


def test_style_serializes_to_telegram_json() -> None:
    kb = build_image_options_keyboard("sess1")
    payload = json.loads(kb.model_dump_json(exclude_none=True))
    assert payload["inline_keyboard"][0][0]["style"] == "success"
    assert payload["inline_keyboard"][1][0]["style"] == "primary"
    assert payload["inline_keyboard"][3][0]["style"] == "danger"
