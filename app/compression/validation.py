"""
app/compression/validation.py

Validates uploaded image files before processing.
Checks magic bytes, file size, pixel count, and decompression bombs.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

# PIL lazy import so tests that mock PIL can work
try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Magic bytes → format
_MAGIC: list[tuple[bytes, int, str]] = [
    (b"\xff\xd8\xff", 0, "JPEG"),
    (b"\x89PNG\r\n\x1a\n", 0, "PNG"),
    (b"RIFF", 0, "WEBP"),    # Also need bytes 8-12 == WEBP
]


@dataclass
class ValidationResult:
    ok: bool
    error_message: str = ""
    format: str = ""
    dimensions: Tuple[int, int] = (0, 0)
    file_size: int = 0
    mode: str = ""


def detect_format_from_magic(path: str) -> Optional[str]:
    """Detect image format from file magic bytes, not extension."""
    try:
        with open(path, "rb") as f:
            header = f.read(16)
    except OSError:
        return None

    if header[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "WEBP"
    return None


def validate_image_file(path: str, max_bytes: int, max_pixels: int) -> ValidationResult:
    """
    Validate an image file at `path`.

    Args:
        path: Filesystem path to the downloaded file.
        max_bytes: Maximum allowed file size in bytes.
        max_pixels: Maximum allowed pixel count (width * height).

    Returns:
        ValidationResult with ok=True if the file passes all checks.
    """
    if not PIL_AVAILABLE:
        return ValidationResult(ok=False, error_message="PIL not available on this system.")

    # 1. File must exist and be non-empty
    try:
        stat = os.stat(path)
    except OSError as e:
        return ValidationResult(ok=False, error_message=f"File not found: {e}")

    file_size = stat.st_size
    if file_size == 0:
        return ValidationResult(ok=False, error_message="The file is empty.")

    # 2. File size limit
    if file_size > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        return ValidationResult(
            ok=False,
            error_message=(
                f"File is too large ({actual_mb:.1f} MB). "
                f"Maximum allowed size is {limit_mb:.0f} MB."
            ),
            file_size=file_size,
        )

    # 3. Magic byte check
    fmt = detect_format_from_magic(path)
    if fmt is None:
        return ValidationResult(
            ok=False,
            error_message=(
                "Unsupported file format. Please send a JPEG, PNG, or WebP image."
            ),
            file_size=file_size,
        )

    # 4. PIL open + decompression bomb + pixel count
    # Temporarily disable the decompression bomb limit so we can give a custom error.
    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None  # We enforce our own limit below
    try:
        try:
            img = Image.open(path)
            img.verify()  # Checks for truncation / corruption
        except UnidentifiedImageError:
            return ValidationResult(
                ok=False,
                error_message="The file appears to be corrupt or is not a valid image.",
                file_size=file_size,
            )
        except Exception as e:
            return ValidationResult(
                ok=False,
                error_message=f"Could not read image: {e}",
                file_size=file_size,
            )

        # Re-open after verify (verify closes the file)
        try:
            img = Image.open(path)
            width, height = img.size
            mode = img.mode
        except Exception as e:
            return ValidationResult(
                ok=False,
                error_message=f"Could not decode image dimensions: {e}",
                file_size=file_size,
            )
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit

    pixels = width * height
    if pixels > max_pixels:
        mp = pixels / 1_000_000
        limit_mp = max_pixels / 1_000_000
        return ValidationResult(
            ok=False,
            error_message=(
                f"Image is too large ({mp:.1f} MP). "
                f"Maximum allowed resolution is {limit_mp:.0f} MP."
            ),
            file_size=file_size,
            format=fmt,
            dimensions=(width, height),
            mode=mode,
        )

    return ValidationResult(
        ok=True,
        format=fmt,
        dimensions=(width, height),
        file_size=file_size,
        mode=mode,
    )
