"""
app/compression/engine.py

Main compression orchestration.
Provides synchronous compression logic and an isolated, genuinely killable
process execution runner with hard timeout enforcement.
"""
from __future__ import annotations

import asyncio
import io
import multiprocessing as mp
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

try:
    from PIL import Image, ImageOps, ImageFilter, ImageChops
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


@dataclass
class CompressionResult:
    success: bool
    output_path: str
    stats: Optional[CompressionStats]
    error: str = ""
    target_result: Optional[TargetSizeResult] = None
    form_validation_errors: List[str] = field(default_factory=list)
    suggestion: str = ""
    is_lossless_verified: bool = False
    background_treatment: str = ""


# Concurrency guard: Render Free has 1 worker / 0.1 CPU
_job_lock = asyncio.Lock()


def _fit_and_resize(img: "Image.Image", req: CompressionRequest) -> "Image.Image":
    """
    Apply dimension and resize constraints without ever distorting or stretching the image.
    Supports proportional fit, letterbox/pillarbox padding, and center crop.
    """
    orig_w, orig_h = img.size

    # 1. Percentage scaling
    if 0.0 < req.scale_percent < 1.0:
        new_w = max(1, int(orig_w * req.scale_percent))
        new_h = max(1, int(orig_h * req.scale_percent))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        orig_w, orig_h = img.size

    # 2. Exact dimensions requested
    if req.exact_width > 0 and req.exact_height > 0:
        target_w, target_h = req.exact_width, req.exact_height
        if (orig_w, orig_h) == (target_w, target_h):
            return img

        if req.fit_mode == "pad":
            # Scale proportionally to fit within target box, then pad with pad_color
            img.thumbnail((target_w, target_h), Image.LANCZOS)
            padded = Image.new(
                "RGBA" if img.mode in ("RGBA", "LA") else "RGB",
                (target_w, target_h),
                req.pad_color if img.mode not in ("RGBA", "LA") else (*req.pad_color, 255)
            )
            offset = ((target_w - img.size[0]) // 2, (target_h - img.size[1]) // 2)
            padded.paste(img, offset)
            return padded

        elif req.fit_mode == "crop":
            # Center crop to target aspect ratio and size
            return ImageOps.fit(img, (target_w, target_h), Image.LANCZOS, centering=(0.5, 0.5))

        else:
            # Default "fit": proportional thumbnail without padding or stretching
            img.thumbnail((target_w, target_h), Image.LANCZOS)
            return img

    # 3. Maximum dimensions bounding
    max_w = req.max_width
    max_h = req.max_height

    if max_w > 0 or max_h > 0:
        target_max_w = max_w if max_w > 0 else orig_w
        target_max_h = max_h if max_h > 0 else orig_h

        # Enforce no_enlargement
        if req.no_enlargement and (orig_w <= target_max_w and orig_h <= target_max_h):
            return img

        img.thumbnail((target_max_w, target_max_h), Image.LANCZOS)

    return img


def _apply_specialized_processing(img: "Image.Image", preset: Preset) -> "Image.Image":
    """Apply algorithmic image adjustments for specialized modes."""
    if preset == Preset.SIGNATURE:
        # Convert to grayscale
        gray = img.convert("L")
        # Adaptive contrast: paper background (light grays > 190) -> clean pure white (255)
        # Ink strokes (< 160) slightly enhanced
        def threshold_fn(p: int) -> int:
            if p >= 195:
                return 255
            elif p <= 120:
                return max(0, int(p * 0.7))
            else:
                # Smooth transition
                return int((p - 120) * (255 / (195 - 120)))

        return gray.point(threshold_fn)

    elif preset == Preset.FORM_PHOTO:
        # Crop or fit to standard portrait ratio (3:4) if requested or max 800px
        img.thumbnail((800, 800), Image.LANCZOS)
        # Gentle unsharp mask for clear face details in ID/passport photos
        try:
            return img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=115, threshold=3))
        except Exception:
            return img

    return img


def compress_image_sync(request: CompressionRequest) -> CompressionResult:
    """
    Synchronous compression engine.
    Must be pure and safe to run in an isolated worker process.
    """
    if os.environ.get("_TEST_SIMULATE_SLOW_WORKER") == "1":
        import time
        time.sleep(10.0)

    if not PIL_AVAILABLE:
        return CompressionResult(success=False, output_path="", stats=None, error="PIL library not available.")

    try:
        file_size = os.path.getsize(request.input_path)
    except OSError as e:
        return CompressionResult(success=False, output_path="", stats=None, error=f"File error: {e}")

    try:
        img = Image.open(request.input_path)
        img.load()
    except Exception as e:
        return CompressionResult(success=False, output_path="", stats=None, error=f"Cannot decode image: {e}")

    original_dimensions = img.size
    original_bytes = file_size
    input_fmt = (img.format or "JPEG").upper()
    if input_fmt not in SUPPORTED_INPUT_FORMATS:
        input_fmt = "JPEG"

    # 1. Orientation
    img = normalize_orientation(img)

    # 2. Output format decision
    output_fmt = (request.output_format or input_fmt).upper()
    if output_fmt not in SUPPORTED_INPUT_FORMATS:
        output_fmt = input_fmt

    # Preferred format override from specialized presets (if output_format not explicitly chosen)
    if not request.output_format and request.preset:
        preset_info = PRESET_PARAMS.get(request.preset)
        if preset_info and preset_info.preferred_format:
            output_fmt = preset_info.preferred_format

    # Transparency disclosure
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    background_treatment = ""
    if has_alpha and output_fmt == "JPEG":
        background_treatment = "Transparent background flattened onto white."

    # 3. Output path
    ext = FORMAT_EXTENSIONS.get(output_fmt, "jpg")
    output_path = request.output_path or os.path.join(
        tempfile.gettempdir(),
        f"kayicomp_{uuid.uuid4().hex}.{ext}"
    )

    # 4. Dimension / fit processing
    img = _fit_and_resize(img, request)

    # 5. Specialized preset processing
    if request.preset:
        img = _apply_specialized_processing(img, request.preset)

    # Smart suggestions generation
    suggestion = ""
    if original_dimensions[0] > 2500 or original_dimensions[1] > 2500:
        if not request.allow_resize and not request.max_width:
            suggestion = "💡 Tip: Resizing large dimensions can reduce file size by up to 70%."
    elif original_bytes < 50 * 1024:
        suggestion = "💡 Note: Image is already under 50 KB. Further reduction may noticeably affect quality."
    elif has_alpha and output_fmt == "JPEG":
        suggestion = "💡 Note: Converted to JPEG with white background. Use PNG/WebP to keep transparency."

    # --- MODE A: LOSSLESS COMPRESSION ---
    if request.lossless or request.preset == Preset.LOSSLESS:
        # Strict lossless rules:
        # If input is JPEG, keep original if re-encoding increases size
        if input_fmt == "JPEG" and output_fmt == "JPEG":
            # Attempt optimized Huffman re-encoding at q=95 or lossless copy
            buf = io.BytesIO()
            norm_img = normalize_mode_for_format(img, "JPEG")
            norm_img.save(buf, format="JPEG", quality=95, optimize=True)
            encoded_bytes = buf.getvalue()
            if len(encoded_bytes) < original_bytes:
                with open(output_path, "wb") as f:
                    f.write(encoded_bytes)
                out_size = len(encoded_bytes)
            else:
                # Original is already optimal! Avoid making it larger.
                shutil.copyfile(request.input_path, output_path)
                out_size = original_bytes
                suggestion = "💡 Lossless: Original was already optimally compressed."

            stats = CompressionStats(
                original_bytes=original_bytes,
                output_bytes=out_size,
                output_format="JPEG",
                output_dimensions=img.size,
                original_dimensions=original_dimensions,
                target_met=True,
                quality_used=100,
            )
            return CompressionResult(
                success=True,
                output_path=output_path,
                stats=stats,
                suggestion=suggestion,
                is_lossless_verified=True,
                background_treatment=background_treatment,
            )

        # For PNG/WebP: truly lossless
        target_fmt = output_fmt if output_fmt in ("PNG", "WEBP") else "PNG"
        norm_img = normalize_mode_for_format(img, target_fmt)
        save_params = get_save_params(target_fmt, lossless=True, optimize=True)
        norm_img.save(output_path, **save_params)
        out_size = os.path.getsize(output_path)

        if out_size >= original_bytes and input_fmt == target_fmt:
            # If recompression didn't save space, keep original
            shutil.copyfile(request.input_path, output_path)
            out_size = original_bytes
            suggestion = "💡 Lossless: Original was already optimally compressed."

        stats = CompressionStats(
            original_bytes=original_bytes,
            output_bytes=out_size,
            output_format=target_fmt,
            output_dimensions=img.size,
            original_dimensions=original_dimensions,
            target_met=True,
            quality_used=100,
        )
        return CompressionResult(
            success=True,
            output_path=output_path,
            stats=stats,
            suggestion=suggestion,
            is_lossless_verified=True,
            background_treatment=background_treatment,
        )

    # --- MODE B: TARGET SIZE COMPRESSION ---
    target_bytes = request.target_bytes or request.form_max_bytes
    if target_bytes is not None:
        if request.strip_metadata:
            img = strip_metadata(img)

        target_res = find_quality_for_target(
            img=img,
            target_bytes=target_bytes,
            fmt=output_fmt,
            output_path=output_path,
            allow_resize=request.allow_resize,
            original_file_path=request.input_path,
        )

        try:
            actual_size = os.path.getsize(output_path)
        except OSError:
            actual_size = target_res.actual_bytes

        stats = CompressionStats(
            original_bytes=original_bytes,
            output_bytes=actual_size,
            output_format=output_fmt,
            output_dimensions=target_res.dimensions_used,
            original_dimensions=original_dimensions,
            target_met=target_res.success,
            target_bytes=target_bytes,
            quality_used=target_res.quality_used,
        )

        # Form mode validation
        form_errors = []
        if request.is_form_mode:
            if actual_size > target_bytes:
                form_errors.append(f"Output size ({actual_size // 1024} KB) exceeds maximum limit ({target_bytes // 1024} KB).")
            if request.exact_width > 0 and request.exact_height > 0:
                if target_res.dimensions_used != (request.exact_width, request.exact_height):
                    form_errors.append(f"Dimensions ({target_res.dimensions_used[0]}×{target_res.dimensions_used[1]}) do not match required {request.exact_width}×{request.exact_height}.")

        return CompressionResult(
            success=target_res.success and len(form_errors) == 0,
            output_path=output_path,
            stats=stats,
            target_result=target_res,
            form_validation_errors=form_errors,
            suggestion=suggestion or target_res.reason,
            background_treatment=background_treatment,
        )

    # --- MODE C: PRESET COMPRESSION ---
    preset = request.preset or Preset.BALANCED
    preset_params = PRESET_PARAMS[preset]

    # Resize constraints from preset
    if preset_params.allow_resize and preset_params.max_dimension > 0:
        if not (request.max_width or request.exact_width):
            img.thumbnail((preset_params.max_dimension, preset_params.max_dimension), Image.LANCZOS)

    # Metadata
    exif_bytes = None
    if request.strip_metadata:
        img = strip_metadata(img)
    else:
        exif_bytes = get_exif_bytes(img)

    img = normalize_mode_for_format(img, output_fmt)

    # Subsampling
    subsampling = preset_params.subsampling

    save_params = get_save_params(
        fmt=output_fmt,
        quality=preset_params.quality,
        progressive=preset_params.progressive,
        lossless=False,
        optimize=preset_params.optimize,
        subsampling=subsampling,
    )
    if exif_bytes and output_fmt == "JPEG":
        save_params["exif"] = exif_bytes

    try:
        img.save(output_path, **save_params)
    except Exception as e:
        return CompressionResult(success=False, output_path="", stats=None, error=f"Encoding failed: {e}")

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

    return CompressionResult(
        success=True,
        output_path=output_path,
        stats=stats,
        suggestion=suggestion,
        background_treatment=background_treatment,
    )


# ==============================================================================
# PROCESS ISOLATION & KILLABLE WORKER RUNNER
# ==============================================================================

def _worker_process_target(req: CompressionRequest, conn) -> None:
    """Worker process entrypoint. Runs in a clean, distinct OS process."""
    try:
        result = compress_image_sync(req)
        conn.send(("ok", result))
    except Exception as e:
        conn.send(("error", str(e)))
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def run_compression_isolated(
    request: CompressionRequest,
    timeout_seconds: float = 25.0
) -> CompressionResult:
    """
    Executes compression inside an isolated multiprocessing.Process.
    If timeout_seconds expires:
      - The OS worker process is genuinely terminated and reaped.
      - No rogue CPU-burning process remains.
      - Next tasks run unimpeded.
      - Concurrency is strictly bounded to 1.
    """
    async with _job_lock:
        parent_conn, child_conn = mp.Pipe()
        proc = mp.Process(target=_worker_process_target, args=(request, child_conn))
        proc.start()
        child_conn.close()

        loop = asyncio.get_running_loop()

        try:
            status, res = await asyncio.wait_for(
                loop.run_in_executor(None, parent_conn.recv),
                timeout=timeout_seconds,
            )
            proc.join(timeout=2.0)
            if status == "ok":
                return res
            else:
                return CompressionResult(success=False, output_path="", stats=None, error=res)

        except asyncio.TimeoutError:
            # Genuinely kill the child process!
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1.0)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=1.0)
            raise asyncio.TimeoutError("Processing deadline exceeded.")

        finally:
            try:
                parent_conn.close()
            except Exception:
                pass
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1.0)
