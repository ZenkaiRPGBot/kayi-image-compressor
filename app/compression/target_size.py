"""
app/compression/target_size.py

Binary search algorithm for target-size compression.
Finds the optimal quality setting to hit a target file size.
"""
from __future__ import annotations

import io
import os
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
    max_iterations: int = 10,
) -> TargetSizeResult:
    """
    Binary search over JPEG/WebP quality to hit target_bytes.

    Strategy:
    1. Try quality binary search (q=5..95) for up to `max_iterations` steps.
    2. If quality search fails and allow_resize=True, try 75%, 50%, 25% dimensions
       at the lowest quality found.
    3. Write the best result to output_path.
    """
    fmt = fmt.upper()
    img = normalize_mode_for_format(img, fmt)
    img = handle_transparency(img, fmt)

    # For PNG/lossless: just encode and check
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
            reason="" if success else f"PNG lossless result ({len(data)} bytes) exceeds target ({target_bytes} bytes).",
        )

    low, high = 5, 95
    best_quality = low
    best_data: Optional[bytes] = None

    for _ in range(max_iterations):
        if low > high:
            break
        mid = (low + high) // 2
        data = _encode_to_bytes(img, fmt, mid)
        size = len(data)

        if size <= target_bytes:
            # Fits — try higher quality
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

    # Quality search failed — try dimension reduction if allowed
    if allow_resize:
        for scale in (0.75, 0.5, 0.25):
            small = _resize_image(img, scale)
            data = _encode_to_bytes(small, fmt, 50)
            if len(data) <= target_bytes:
                with open(output_path, "wb") as f:
                    f.write(data)
                return TargetSizeResult(
                    success=True,
                    output_path=output_path,
                    actual_bytes=len(data),
                    quality_used=50,
                    dimensions_used=small.size,
                    reason=f"Resized to {int(scale*100)}% of original dimensions to meet target.",
                )

    # Complete failure — write smallest result
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
            "Try enabling resize or choosing a larger target."
        ),
    )
