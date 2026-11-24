"""
tests/test_formats.py

Tests for format conversion, transparency handling, and save params.
"""
import io
import pytest
from PIL import Image

from app.compression.formats import (
    get_save_params,
    handle_transparency,
    normalize_mode_for_format,
    FORMAT_EXTENSIONS,
)


class TestGetSaveParams:
    def test_jpeg_params(self):
        p = get_save_params("JPEG", quality=80)
        assert p["format"] == "JPEG"
        assert p["quality"] == 80
        assert p.get("progressive") is True

    def test_png_params(self):
        p = get_save_params("PNG", quality=85)
        assert p["format"] == "PNG"
        assert "compress_level" in p

    def test_webp_params(self):
        p = get_save_params("WEBP", quality=70)
        assert p["format"] == "WEBP"
        assert p["quality"] == 70

    def test_webp_lossless(self):
        p = get_save_params("WEBP", lossless=True)
        assert p["lossless"] is True

    def test_jpeg_quality_clamped(self):
        p = get_save_params("JPEG", quality=200)
        assert p["quality"] == 95
        p2 = get_save_params("JPEG", quality=-5)
        assert p2["quality"] == 1

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            get_save_params("GIF")


class TestTransparencyHandling:
    def test_rgba_to_jpeg_flattened(self):
        img = Image.new("RGBA", (100, 100), (200, 100, 50, 128))
        result = handle_transparency(img, "JPEG")
        assert result.mode == "RGB"

    def test_rgb_jpeg_unchanged(self):
        img = Image.new("RGB", (100, 100), (200, 100, 50))
        result = handle_transparency(img, "JPEG")
        assert result.mode == "RGB"

    def test_rgba_to_png_preserved(self):
        img = Image.new("RGBA", (100, 100), (200, 100, 50, 128))
        result = handle_transparency(img, "PNG")
        assert result.mode == "RGBA"

    def test_rgba_to_webp_preserved(self):
        img = Image.new("RGBA", (100, 100), (200, 100, 50, 200))
        result = handle_transparency(img, "WEBP")
        assert result.mode == "RGBA"


class TestNormalizeModeForFormat:
    def test_rgb_jpeg_ok(self):
        img = Image.new("RGB", (50, 50))
        result = normalize_mode_for_format(img, "JPEG")
        assert result.mode in ("RGB", "L")

    def test_rgba_jpeg_converts(self):
        img = Image.new("RGBA", (50, 50))
        result = normalize_mode_for_format(img, "JPEG")
        assert result.mode in ("RGB", "L")

    def test_palette_png_converts(self):
        img = Image.new("P", (50, 50))
        result = normalize_mode_for_format(img, "PNG")
        assert result.mode in ("RGB", "RGBA", "L", "LA")


class TestFormatExtensions:
    def test_known_formats(self):
        assert FORMAT_EXTENSIONS["JPEG"] == "jpg"
        assert FORMAT_EXTENSIONS["PNG"] == "png"
        assert FORMAT_EXTENSIONS["WEBP"] == "webp"
