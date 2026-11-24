"""
app/compression/metadata.py

EXIF metadata handling — read, normalize orientation, strip, preserve.
"""
from __future__ import annotations

from typing import Optional

try:
    from PIL import Image, ExifTags
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# EXIF orientation tag ID
_ORIENTATION_TAG = 274  # 0x0112


def normalize_orientation(img: "Image.Image") -> "Image.Image":
    """
    Apply EXIF orientation to rotate/flip the image, then remove the tag.
    Returns the corrected image. Safe to call on images without EXIF.
    """
    try:
        exif = img._getexif()  # type: ignore[attr-defined]
        if exif is None:
            return img
        orientation = exif.get(_ORIENTATION_TAG)
        if orientation is None:
            return img

        ops = {
            2: (Image.FLIP_LEFT_RIGHT,),
            3: (Image.ROTATE_180,),
            4: (Image.FLIP_TOP_BOTTOM,),
            5: (Image.TRANSPOSE,),
            6: (Image.ROTATE_270,),
            7: (Image.TRANSVERSE,),
            8: (Image.ROTATE_90,),
        }
        if orientation in ops:
            for op in ops[orientation]:
                img = img.transpose(op)
    except (AttributeError, Exception):
        pass
    return img


def strip_metadata(img: "Image.Image") -> "Image.Image":
    """
    Return a copy of the image with no EXIF metadata.
    Creates a fresh image with identical pixel data but stripped headers/metadata.
    """
    new_img = Image.new(img.mode, img.size)
    new_img.paste(img)
    return new_img


def get_exif_bytes(img: "Image.Image") -> Optional[bytes]:
    """Return raw EXIF bytes from an image, or None."""
    try:
        exif = img.info.get("exif")
        if exif:
            return exif
        return None
    except Exception:
        return None
