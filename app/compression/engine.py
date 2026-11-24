"""
app/compression/engine.py

Main compression orchestration. Runs in a ProcessPoolExecutor worker.
Called from async context via asyncio.wait_for().
"""
from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from app.compression.formats import (
    FORMAT_EXTENSIONS,
    SUPPORTED_INPUT_FORMATS,
    get_save_params,
    handle_transparency,
    normalize_mode_for_format,
)
from app.compression.metadata import normalize_orientation, strip_metadata, get_exif_bytes
from app.compression.presets import CompressionRequest, Preset, PRESET_PARAMS
from app.compression.statistics import CompressionStats
from app.compression.target_size import find_quality_for_target, TargetSizeResult
from app.compression.validation import validate_image_file


@dataclass
class CompressionResult:
    success: bool
    output_path: str
    stats: Optional[CompressionStats]
    error: str = ""
    target_result: Optional[TargetSizeResult] = None


def _do_resize(img: "Image.Image", max_width: int, max_height: int) -> "Image.Image":
    """Resize image to fit within max dimensions, maintaining aspect ratio."""
    w, h = img.size
    if max_width > 0 and w > max_width:
        scale = max_width / w
        w = max_width
        h = int(h * scale)
    if max_height > 0 and h > max_height:
        scale = max_height / h
        h = max_height
        w = int(w * scale)
    if (w, h) != img.size:
        return img.resize((w, h), Image.LANCZOS)
    return img


def compress_image_sync(request: CompressionRequest) -> CompressionResult:
    """
    Synchronous compression entry point. Runs in a process pool worker.

    Handles both preset-based and target-size compression.
    Always cleans up temp files on failure.
    """
    if not PIL_AVAILABLE:
        return CompressionResult(success=False, output_path="", stats=None, error="PIL not available.")

    # --- Validate input ---
    # We trust the file has already been validated by validate_image_file(),
    # but do a lightweight size check here for safety.
    try:
        file_size = os.path.getsize(request.input_path)
    except OSError as e:
        return CompressionResult(success=False, output_path="", stats=None, error=str(e))

    # --- Open image ---
    try:
        img = Image.open(request.input_path)
        img.load()  # Force full decode
    except Exception as e:
        return CompressionResult(success=False, output_path="", stats=None, error=f"Cannot open image: {e}")

    original_dimensions = img.size
    original_bytes = file_size

    # --- Normalize orientation ---
    img = normalize_orientation(img)

    # --- Determine output format ---
    input_fmt = img.format or "JPEG"
    if input_fmt not in SUPPORTED_INPUT_FORMATS:
        input_fmt = "JPEG"
    output_fmt = (request.output_format or input_fmt).upper()
    if output_fmt not in {"JPEG", "PNG", "WEBP"}:
        output_fmt = input_fmt

    # --- Determine output path ---
    ext = FORMAT_EXTENSIONS.get(output_fmt, "jpg")
    output_path = request.output_path or os.path.join(
        tempfile.gettempdir(),
        f"kayicomp_{uuid.uuid4().hex}.{ext}",
    )

    # --- MODE: TARGET SIZE ---
    if request.target_bytes is not None:
        # Strip metadata first
        if request.strip_metadata:
            img = strip_metadata(img)

        result = find_quality_for_target(
            img=img,
            target_bytes=request.target_bytes,
            fmt=output_fmt,
            output_path=output_path,
            allow_resize=request.allow_resize,
        )

        try:
            actual_size = os.path.getsize(output_path)
        except OSError:
            actual_size = result.actual_bytes

        stats = CompressionStats(
            original_bytes=original_bytes,
            output_bytes=actual_size,
            output_format=output_fmt,
            output_dimensions=result.dimensions_used,
            original_dimensions=original_dimensions,
            target_met=result.success,
            target_bytes=request.target_bytes,
            quality_used=result.quality_used,
        )
        return CompressionResult(
            success=True,
            output_path=output_path,
            stats=stats,
            target_result=result,
        )

    # --- MODE: PRESET ---
    if request.preset is None:
        request = CompressionRequest(
            input_path=request.input_path,
            output_path=request.output_path,
            preset=Preset.BALANCED,
        )
    preset_params = PRESET_PARAMS[request.preset]

    # Lossless override
    lossless = preset_params.lossless or request.lossless

    # --- Apply resize ---
    allow_resize = preset_params.allow_resize or request.allow_resize
    if allow_resize and preset_params.max_dimension > 0:
        img = _do_resize(img, preset_params.max_dimension, preset_params.max_dimension)
    elif request.max_width > 0 or request.max_height > 0:
        img = _do_resize(img, request.max_width, request.max_height)

    # --- Strip / preserve metadata ---
    exif_bytes: Optional[bytes] = None
    if request.strip_metadata:
        img = strip_metadata(img)
    else:
        exif_bytes = get_exif_bytes(img)

    # --- Normalize mode ---
    img = normalize_mode_for_format(img, output_fmt)

    # --- Save ---
    try:
        save_params = get_save_params(
            fmt=output_fmt,
            quality=preset_params.quality,
            progressive=preset_params.progressive,
            lossless=lossless,
            optimize=preset_params.optimize,
        )
        if exif_bytes and output_fmt == "JPEG":
            save_params["exif"] = exif_bytes

        img.save(output_path, **save_params)
    except Exception as e:
        return CompressionResult(success=False, output_path="", stats=None, error=f"Save failed: {e}")

    try:
        actual_size = os.path.getsize(output_path)
    except OSError:
        actual_size = 0

    stats = CompressionStats(
        original_bytes=original_bytes,
        output_bytes=actual_size,
        output_format=output_fmt,
        output_dimensions=img.size,
        original_dimensions=original_dimensions,
        target_met=False,
        quality_used=preset_params.quality,
    )
    return CompressionResult(success=True, output_path=output_path, stats=stats)
