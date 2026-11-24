"""
app/compression/formats.py

Format-specific save parameters and transparency handling.
"""
from __future__ import annotations

from typing import Dict, Any, Optional, Tuple

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

SUPPORTED_INPUT_FORMATS = {"JPEG", "PNG", "WEBP"}
SUPPORTED_OUTPUT_FORMATS = {"JPEG", "PNG", "WEBP"}

# Map PIL format name → file extension
FORMAT_EXTENSIONS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}

# Default MIME types
FORMAT_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def get_save_params(
    fmt: str,
    quality: int = 85,
    progressive: bool = True,
    lossless: bool = False,
    optimize: bool = True,
) -> Dict[str, Any]:
    """
    Return PIL Image.save() keyword arguments for the given format.

    Args:
        fmt: "JPEG", "PNG", or "WEBP"
        quality: 1-95 for JPEG/WebP (ignored for lossless PNG)
        progressive: Enable progressive encoding for JPEG
        lossless: Use lossless compression (WebP / PNG)
        optimize: Enable optimizer pass (JPEG/PNG)
    """
    fmt = fmt.upper()
    if fmt == "JPEG":
        params: Dict[str, Any] = {
            "format": "JPEG",
            "quality": max(1, min(95, quality)),
            "optimize": optimize,
        }
        if progressive:
            params["progressive"] = True
        return params

    if fmt == "PNG":
        # PNG quality maps to compress_level 0-9 (inverse: higher quality = lower compression)
        compress_level = max(0, min(9, 9 - round(quality / 10.5)))
        return {
            "format": "PNG",
            "optimize": optimize,
            "compress_level": compress_level,
        }

    if fmt == "WEBP":
        if lossless:
            return {"format": "WEBP", "lossless": True, "quality": 100}
        return {
            "format": "WEBP",
            "quality": max(1, min(95, quality)),
            "method": 4,  # Balanced speed/quality tradeoff
        }

    raise ValueError(f"Unsupported format: {fmt}")


def handle_transparency(
    img: "Image.Image",
    target_format: str,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
) -> "Image.Image":
    """
    Handle transparency when converting to a format that doesn't support it.

    For JPEG output: flatten alpha channel onto a white background.
    For PNG/WebP output: preserve transparency.

    Returns the processed image.
    """
    target_format = target_format.upper()
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )

    if not has_alpha:
        return img

    if target_format == "JPEG":
        # Flatten alpha onto white background
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, bg_color)
            if img.mode == "LA":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            return background
        # Fallback
        return img.convert("RGB")

    # PNG and WEBP support transparency — ensure RGBA mode
    if img.mode == "P":
        return img.convert("RGBA")
    if img.mode == "LA":
        return img.convert("RGBA")

    return img


def normalize_mode_for_format(img: "Image.Image", target_format: str) -> "Image.Image":
    """
    Ensure the image mode is compatible with the target format.
    Converts palette / unusual modes to RGB or RGBA as appropriate.
    """
    target_format = target_format.upper()
    if target_format == "JPEG":
        if img.mode not in ("RGB", "L", "CMYK", "YCbCr"):
            img = handle_transparency(img, "JPEG")
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
    elif target_format in ("PNG", "WEBP"):
        if img.mode == "P":
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        elif img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGB")
    return img
