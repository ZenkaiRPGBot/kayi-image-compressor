"""
tests/test_validation.py

Tests for app/compression/validation.py
"""
import os
import pytest
from app.compression.validation import validate_image_file, detect_format_from_magic

MAX_BYTES = 8 * 1024 * 1024  # 8 MB
MAX_PIXELS = 12_000_000


class TestDetectFormat:
    def test_jpeg_magic(self, tmp_jpeg):
        fmt = detect_format_from_magic(tmp_jpeg)
        assert fmt == "JPEG"

    def test_png_magic(self, tmp_png):
        fmt = detect_format_from_magic(tmp_png)
        assert fmt == "PNG"

    def test_webp_magic(self, tmp_webp):
        fmt = detect_format_from_magic(tmp_webp)
        assert fmt == "WEBP"

    def test_invalid_returns_none(self, tmp_path):
        p = str(tmp_path / "fake.jpg")
        with open(p, "wb") as f:
            f.write(b"not an image at all")
        assert detect_format_from_magic(p) is None

    def test_missing_file_returns_none(self):
        assert detect_format_from_magic("/nonexistent/path/file.jpg") is None


class TestValidateImageFile:
    def test_valid_jpeg(self, tmp_jpeg):
        result = validate_image_file(tmp_jpeg, MAX_BYTES, MAX_PIXELS)
        assert result.ok
        assert result.format == "JPEG"
        assert result.dimensions[0] > 0
        assert result.file_size > 0

    def test_valid_png(self, tmp_png):
        result = validate_image_file(tmp_png, MAX_BYTES, MAX_PIXELS)
        assert result.ok
        assert result.format == "PNG"

    def test_valid_png_alpha(self, tmp_png_alpha):
        result = validate_image_file(tmp_png_alpha, MAX_BYTES, MAX_PIXELS)
        assert result.ok

    def test_valid_webp(self, tmp_webp):
        result = validate_image_file(tmp_webp, MAX_BYTES, MAX_PIXELS)
        assert result.ok
        assert result.format == "WEBP"

    def test_file_too_large(self, tmp_jpeg):
        result = validate_image_file(tmp_jpeg, max_bytes=10, max_pixels=MAX_PIXELS)
        assert not result.ok
        assert "too large" in result.error_message.lower()

    def test_empty_file(self, tmp_path):
        p = str(tmp_path / "empty.jpg")
        open(p, "wb").close()
        result = validate_image_file(p, MAX_BYTES, MAX_PIXELS)
        assert not result.ok
        assert "empty" in result.error_message.lower()

    def test_missing_file(self):
        result = validate_image_file("/nonexistent.jpg", MAX_BYTES, MAX_PIXELS)
        assert not result.ok

    def test_corrupt_file(self, tmp_path):
        p = str(tmp_path / "corrupt.jpg")
        with open(p, "wb") as f:
            f.write(b"\xff\xd8\xff" + b"\x00" * 100)  # Valid magic, corrupt body
        result = validate_image_file(p, MAX_BYTES, MAX_PIXELS)
        assert not result.ok

    def test_pixel_limit(self, tmp_path):
        from PIL import Image
        import io
        # Create a 4000×4000 = 16 MP image (exceeds 12 MP limit)
        img = Image.new("RGB", (4000, 4000), color=(100, 100, 100))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)
        p = str(tmp_path / "huge.jpg")
        with open(p, "wb") as f:
            f.write(buf.getvalue())
        result = validate_image_file(p, MAX_BYTES, 12_000_000)
        assert not result.ok
        assert "megapixel" in result.error_message.lower() or "MP" in result.error_message

    def test_animated_image_rejected(self, tmp_path):
        from PIL import Image
        import io
        # Create an animated multi-frame WebP
        frames = [Image.new("RGB", (100, 100), (255, 0, 0)), Image.new("RGB", (100, 100), (0, 255, 0))]
        buf = io.BytesIO()
        frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:], duration=200, loop=0)
        p = str(tmp_path / "animated.webp")
        with open(p, "wb") as f:
            f.write(buf.getvalue())
        result = validate_image_file(p, MAX_BYTES, MAX_PIXELS)
        assert not result.ok
        assert "animated" in result.error_message.lower()
