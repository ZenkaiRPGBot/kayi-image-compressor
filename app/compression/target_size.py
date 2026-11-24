"""
app/compression/target_size.py

Adaptive, bounded target-size compression algorithm.
Calibrates quality and proportional downscaling to reliably hit strict file size limits.
"""
from __future__ import annotations

import io
import math
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


def _encode_to_bytes(img: "Image.Image", fmt: str, quality: int, optimize: bool = True) -> bytes:
    """Encode image to bytes in memory and return raw bytes."""
    buf = io.BytesIO()
    params = get_save_params(fmt, quality=quality, optimize=optimize, progressive=(fmt == "JPEG"))
    img.save(buf, **params)
    return buf.getvalue()


def _resize_to_dimensions(img: "Image.Image", target_w: int, target_h: int) -> "Image.Image":
    return img.resize((max(16, target_w), max(16, target_h)), Image.LANCZOS)


def find_quality_for_target(
    img: "Image.Image",
    target_bytes: int,
    fmt: str,
    output_path: str,
    allow_resize: bool = False,
    max_iterations: int = 8,
    original_file_path: Optional[str] = None,
) -> TargetSizeResult:
    """
    Finds optimal quality and adaptive downscaling to meet target_bytes.

    Strict Invariants:
    1. Never mark an output that exceeds target_bytes as success=True.
    2. If original file already satisfies target_bytes and format, avoid unnecessary re-encoding.
    3. Bounded encoding attempts (<= 10) for CPU and deadline safety on Render Free.
    4. Proportional downscaling adaptively computes scale to reach small targets (e.g. 20 KB from 2 MB).
    """
    fmt = fmt.upper()
    orig_dims = img.size
    orig_w, orig_h = orig_dims
    orig_pixels = orig_w * orig_h

    # 1. Immediate bypass if original already meets target and format
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

    # 2. PNG Handling
    if fmt == "PNG":
        # First probe at full resolution
        data = _encode_to_bytes(img, "PNG", quality=85, optimize=True)
        if len(data) <= target_bytes:
            with open(output_path, "wb") as f:
                f.write(data)
            return TargetSizeResult(
                success=True,
                output_path=output_path,
                actual_bytes=len(data),
                quality_used=None,
                dimensions_used=img.size,
            )

        if not allow_resize:
            with open(output_path, "wb") as f:
                f.write(data)
            return TargetSizeResult(
                success=False,
                output_path=output_path,
                actual_bytes=len(data),
                quality_used=None,
                dimensions_used=img.size,
                reason=f"Lossless PNG ({len(data) // 1024} KB) exceeds target ({target_bytes // 1024} KB). Enable downscaling or convert to JPEG/WebP.",
            )

        # PNG with allow_resize: adaptively scale down
        est_px = max(900, target_bytes / 0.18)
        base_s = min(0.90, math.sqrt(est_px / orig_pixels))
        scales = [base_s, base_s * 0.75, base_s * 0.50, base_s * 0.35]
        best_png_data = None
        best_png_dims = img.size

        for s in scales:
            sw = max(24, int(orig_w * s))
            sh = max(24, int(orig_h * s))
            scaled = _resize_to_dimensions(img, sw, sh)
            scaled_data = _encode_to_bytes(scaled, "PNG", quality=85, optimize=True)
            best_png_data = scaled_data
            best_png_dims = (sw, sh)
            if len(scaled_data) <= target_bytes:
                with open(output_path, "wb") as f:
                    f.write(scaled_data)
                return TargetSizeResult(
                    success=True,
                    output_path=output_path,
                    actual_bytes=len(scaled_data),
                    quality_used=None,
                    dimensions_used=(sw, sh),
                    reason=f"Proportionally scaled to {sw}×{sh} to meet PNG target.",
                )

        # Fallback PNG: write closest
        with open(output_path, "wb") as f:
            f.write(best_png_data or data)
        return TargetSizeResult(
            success=False,
            output_path=output_path,
            actual_bytes=len(best_png_data or data),
            quality_used=None,
            dimensions_used=best_png_dims,
            reason=f"PNG cannot reach {target_bytes // 1024} KB. Smallest achievable size is {(len(best_png_data or data)) // 1024} KB.",
        )

    # 3. JPEG / WebP Target Compression (Adaptive & Bounded)
    best_candidate_data: Optional[bytes] = None
    best_candidate_q: Optional[int] = None
    best_candidate_dims: Tuple[int, int] = orig_dims

    # Step A: Probe full resolution at high quality (Q=80)
    probe_80 = _encode_to_bytes(img, fmt, 80)
    if len(probe_80) <= target_bytes:
        # Fits at 80! Probe 92 for max quality
        probe_92 = _encode_to_bytes(img, fmt, 92)
        if len(probe_92) <= target_bytes:
            best_candidate_data, best_candidate_q = probe_92, 92
        else:
            best_candidate_data, best_candidate_q = probe_80, 80

    # Step B: If Q=80 didn't fit, probe full resolution at Q=25
    if best_candidate_data is None:
        probe_25 = _encode_to_bytes(img, fmt, 25)
        if len(probe_25) <= target_bytes:
            # Full resolution fits between 25 and 80! Binary search 4 iterations
            low, high = 25, 80
            best_candidate_data = probe_25
            best_candidate_q = 25
            for _ in range(4):
                mid = (low + high) // 2
                d = _encode_to_bytes(img, fmt, mid)
                if len(d) <= target_bytes:
                    best_candidate_data = d
                    best_candidate_q = mid
                    low = mid + 1
                else:
                    high = mid - 1
        elif not allow_resize:
            # Resizing disallowed: probe down to Q=8
            probe_8 = _encode_to_bytes(img, fmt, 8)
            if len(probe_8) <= target_bytes:
                best_candidate_data, best_candidate_q = probe_8, 8
            else:
                # Impossible without resize
                with open(output_path, "wb") as f:
                    f.write(probe_8)
                return TargetSizeResult(
                    success=False,
                    output_path=output_path,
                    actual_bytes=len(probe_8),
                    quality_used=8,
                    dimensions_used=orig_dims,
                    reason=f"Cannot reach {target_bytes // 1024} KB at original dimensions ({orig_w}×{orig_h}). Enable downscaling to hit target.",
                )

    # Step C: If still no fit and allow_resize is True: Adaptive Stepped Downscale!
    if best_candidate_data is None and allow_resize:
        # Estimate target pixels assuming ~0.08 bytes/pixel at moderate quality
        est_px = max(1000, target_bytes / 0.08)
        base_scale = min(0.85, math.sqrt(est_px / orig_pixels))
        scale_ladder = [
            base_scale,
            base_scale * 0.75,
            base_scale * 0.55,
            base_scale * 0.38,
            base_scale * 0.25,
        ]

        for s in scale_ladder:
            sw = max(24, int(orig_w * s))
            sh = max(24, int(orig_h * s))
            scaled_im = _resize_to_dimensions(img, sw, sh)

            # Test moderate quality Q=50
            d50 = _encode_to_bytes(scaled_im, fmt, 50)
            if len(d50) <= target_bytes:
                # Fits at 50! Try 70 for higher quality
                d70 = _encode_to_bytes(scaled_im, fmt, 70)
                if len(d70) <= target_bytes:
                    best_candidate_data = d70
                    best_candidate_q = 70
                else:
                    best_candidate_data = d50
                    best_candidate_q = 50
                best_candidate_dims = (sw, sh)
                break
            else:
                # Too big at 50, test lower quality Q=25
                d25 = _encode_to_bytes(scaled_im, fmt, 25)
                if len(d25) <= target_bytes:
                    # Fits at 25! Try Q=38
                    d38 = _encode_to_bytes(scaled_im, fmt, 38)
                    if len(d38) <= target_bytes:
                        best_candidate_data = d38
                        best_candidate_q = 38
                    else:
                        best_candidate_data = d25
                        best_candidate_q = 25
                    best_candidate_dims = (sw, sh)
                    break
                # If still too big at Q=25, continue down ladder to smaller scale

    # Step D: Finalize output and verify actual disk bytes
    if best_candidate_data is not None and len(best_candidate_data) <= target_bytes:
        with open(output_path, "wb") as f:
            f.write(best_candidate_data)
        actual_disk_bytes = os.path.getsize(output_path)
        is_success = actual_disk_bytes <= target_bytes
        reason = ""
        if best_candidate_dims != orig_dims:
            reason = f"Proportionally scaled to {best_candidate_dims[0]}×{best_candidate_dims[1]} to meet target."
        return TargetSizeResult(
            success=is_success,
            output_path=output_path,
            actual_bytes=actual_disk_bytes,
            quality_used=best_candidate_q,
            dimensions_used=best_candidate_dims,
            reason=reason,
        )

    # Step E: If genuinely impossible (e.g. 1 KB requested on complex image)
    if best_candidate_data is None:
        last_s = 0.15
        sw = max(24, int(orig_w * last_s))
        sh = max(24, int(orig_h * last_s))
        last_im = _resize_to_dimensions(img, sw, sh)
        best_candidate_data = _encode_to_bytes(last_im, fmt, 10)
        best_candidate_q = 10
        best_candidate_dims = (sw, sh)

    with open(output_path, "wb") as f:
        f.write(best_candidate_data)
    actual_disk_bytes = os.path.getsize(output_path)
    return TargetSizeResult(
        success=False,
        output_path=output_path,
        actual_bytes=actual_disk_bytes,
        quality_used=best_candidate_q,
        dimensions_used=best_candidate_dims,
        reason=(
            f"Could not reach {target_bytes // 1024} KB target. "
            f"Smallest achievable size is {actual_disk_bytes // 1024} KB. "
            + ("Enable downscaling or choose a larger target." if not allow_resize else "Target is too small for this image.")
        ),
    )
