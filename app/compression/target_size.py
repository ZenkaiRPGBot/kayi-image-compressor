"""
app/compression/target_size.py

Binary search algorithm for target-size compression.
Finds the optimal quality setting to hit a target file size.
"""
from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from app.compression.formats import get_save_params, handle_transparency, normalize_mode_for_format


@dataclass
class TargetSizeResult:
    success: bool
    output_path: str
    actual_bytes: int
    quality_used: Optional[int]
    dimensions_used: Tuple[int, int]
    reason: str = ""
    already_compliant: bool = False


def _encode_to_bytes(img: "Image.Image", fmt: str, quality: int) -> bytes:
    """Encode image to bytes in memory and return raw bytes."""
    buf = io.BytesIO()
    params = get_save_params(fmt, quality=quality, progressive=(fmt == "JPEG"))
    img.save(buf, **params)
    return buf.getvalue()


def _resize_image(img: "Image.Image", scale: float) -> "Image.Image":
    """Resize image to `scale` fraction of original, maintaining aspect ratio."""
    w, h = img.size
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return img.resize((new_w, new_h), Image.LANCZOS)


def find_quality_for_target(
    img: "Image.Image",
    target_bytes: int,
    fmt: str,
    output_path: str,
    allow_resize: bool = False,
    max_iterations: int = 7,
    original_file_path: Optional[str] = None,
) -> TargetSizeResult:
    """
    Binary search over JPEG/WebP quality to hit target_bytes.

    Strict rules:
    - Never mark an output that exceeds target_bytes as success=True.
    - If original file already satisfies target_bytes and format, avoid unnecessary re-encoding.
    - Bound iterations to max_iterations (default 7) for CPU safety.
    """
    fmt = fmt.upper()
    orig_dims = img.size

    # Check if original already satisfies target and format
    if original_file_path and os.path.exists(original_file_path):
        orig_size = os.path.getsize(original_file_path)
        orig_fmt = (img.format or "").upper()
        if orig_size <= target_bytes and (orig_fmt == fmt or not fmt):
            shutil.copyfile(original_file_path, output_path)
            return TargetSizeResult(
                success=True,
                output_path=output_path,
                actual_bytes=orig_size,
                quality_used=None,
                dimensions_used=orig_dims,
                reason="Original image already meets the target size.",
                already_compliant=True,
            )

    img = normalize_mode_for_format(img, fmt)
    img = handle_transparency(img, fmt)

    # For PNG/lossless: encode with max compression
    if fmt == "PNG":
        buf = io.BytesIO()
        params = get_save_params(fmt, quality=85, optimize=True)
        img.save(buf, **params)
        data = buf.getvalue()
        with open(output_path, "wb") as f:
            f.write(data)
        success = len(data) <= target_bytes
        return TargetSizeResult(
            success=success,
            output_path=output_path,
            actual_bytes=len(data),
            quality_used=None,
            dimensions_used=img.size,
            reason="" if success else f"PNG lossless size ({len(data) // 1024} KB) exceeds target ({target_bytes // 1024} KB). Try JPEG/WebP or enable resizing.",
        )

    # Binary search over quality [5..95]
    low, high = 5, 95
    best_quality: Optional[int] = None
    best_data: Optional[bytes] = None

    for _ in range(max_iterations):
        if low > high:
            break
        mid = (low + high) // 2
        data = _encode_to_bytes(img, fmt, mid)
        size = len(data)

        if size <= target_bytes:
            # Fits — save and try higher quality
            best_quality = mid
            best_data = data
            low = mid + 1
        else:
            # Too big — try lower quality
            high = mid - 1

    if best_data is not None and len(best_data) <= target_bytes:
        with open(output_path, "wb") as f:
            f.write(best_data)
        return TargetSizeResult(
            success=True,
            output_path=output_path,
            actual_bytes=len(best_data),
            quality_used=best_quality,
            dimensions_used=img.size,
        )

    # Quality search alone failed — try dimension reduction if allowed
    if allow_resize:
        for scale in (0.75, 0.50, 0.35, 0.25):
            small = _resize_image(img, scale)
            # Try at quality 60 first for good visual fidelity
            data = _encode_to_bytes(small, fmt, 60)
            if len(data) <= target_bytes:
                with open(output_path, "wb") as f:
                    f.write(data)
                return TargetSizeResult(
                    success=True,
                    output_path=output_path,
                    actual_bytes=len(data),
                    quality_used=60,
                    dimensions_used=small.size,
                    reason=f"Resized to {int(scale * 100)}% of original dimensions to meet target.",
                )
            # Try lowest quality at this scale
            data = _encode_to_bytes(small, fmt, 20)
            if len(data) <= target_bytes:
                with open(output_path, "wb") as f:
                    f.write(data)
                return TargetSizeResult(
                    success=True,
                    output_path=output_path,
                    actual_bytes=len(data),
                    quality_used=20,
                    dimensions_used=small.size,
                    reason=f"Resized to {int(scale * 100)}% at lower quality to meet target.",
                )

    # If completely unattainable: encode at q=5, write output, but strictly return success=False
    if best_data is None:
        best_data = _encode_to_bytes(img, fmt, 5)
        best_quality = 5

    with open(output_path, "wb") as f:
        f.write(best_data)

    target_kb = target_bytes / 1024
    actual_kb = len(best_data) / 1024
    return TargetSizeResult(
        success=False,
        output_path=output_path,
        actual_bytes=len(best_data),
        quality_used=best_quality,
        dimensions_used=img.size,
        reason=(
            f"Could not reach {target_kb:.0f} KB target. "
            f"Smallest achievable size is {actual_kb:.0f} KB. "
            + ("Try enabling resize or choosing a larger target." if not allow_resize else "The image has too much detail for this target.")
        ),
    )
