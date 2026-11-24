"""
app/compression/presets.py

Compression preset definitions and CompressionRequest dataclass.
Includes quality presets, specialized modes, and form upload parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class Preset(str, Enum):
    # Standard Quality Presets
    BEST_QUALITY = "best_quality"
    BALANCED = "balanced"
    SMALLEST = "smallest"
    LOSSLESS = "lossless"

    # Specialized Modes
    PHOTO = "photo"
    SCREENSHOT = "screenshot"
    SIGNATURE = "signature"
    FORM_PHOTO = "form_photo"
    TRANSPARENT = "transparent"


@dataclass
class CompressionRequest:
    """All parameters for a single compression job."""
    input_path: str
    output_path: str

    # Compression mode — either preset OR target_bytes
    preset: Optional[Preset] = None
    target_bytes: Optional[int] = None

    # Output format: "JPEG", "PNG", "WEBP", or "" to keep original
    output_format: str = ""

    # Dimension & Resize constraints
    max_width: int = 0
    max_height: int = 0
    exact_width: int = 0
    exact_height: int = 0
    scale_percent: float = 1.0      # 1.0 = 100%, 0.75 = 75%, etc.
    allow_resize: bool = False
    no_enlargement: bool = True     # Never upscale smaller images
    keep_aspect_ratio: bool = True

    # Fit mode when aspect ratio or exact dimension differs:
    # "fit" (proportional scale), "pad" (proportional scale + letterbox/pillarbox), "crop" (center crop)
    # Never stretch!
    fit_mode: str = "fit"
    pad_color: Tuple[int, int, int] = (255, 255, 255)

    # Form Upload Mode
    is_form_mode: bool = False
    form_max_bytes: Optional[int] = None

    # Metadata
    strip_metadata: bool = True

    # Lossless mode
    lossless: bool = False


# --- Preset parameters ---

@dataclass
class PresetParams:
    quality: int
    allow_resize: bool
    max_dimension: int        # 0 = no limit
    progressive: bool
    optimize: bool
    lossless: bool
    subsampling: Optional[int] = None  # None = default, 0 = 4:4:4 (no chroma subsampling)
    preferred_format: Optional[str] = None


PRESET_PARAMS: dict[Preset, PresetParams] = {
    Preset.BEST_QUALITY: PresetParams(
        quality=85,
        allow_resize=False,
        max_dimension=0,
        progressive=True,
        optimize=True,
        lossless=False,
    ),
    Preset.BALANCED: PresetParams(
        quality=75,
        allow_resize=True,
        max_dimension=2048,
        progressive=True,
        optimize=True,
        lossless=False,
    ),
    Preset.SMALLEST: PresetParams(
        quality=45,
        allow_resize=True,
        max_dimension=1280,
        progressive=True,
        optimize=True,
        lossless=False,
    ),
    Preset.LOSSLESS: PresetParams(
        quality=100,
        allow_resize=False,
        max_dimension=0,
        progressive=False,
        optimize=True,
        lossless=True,
    ),
    Preset.PHOTO: PresetParams(
        quality=80,
        allow_resize=True,
        max_dimension=2560,
        progressive=True,
        optimize=True,
        lossless=False,
        preferred_format="JPEG",
    ),
    Preset.SCREENSHOT: PresetParams(
        quality=88,
        allow_resize=False,
        max_dimension=0,
        progressive=True,
        optimize=True,
        lossless=False,
        subsampling=0,  # 4:4:4 subsampling preserves crisp text & UI lines without color bleed
    ),
    Preset.SIGNATURE: PresetParams(
        quality=90,
        allow_resize=True,
        max_dimension=1000,
        progressive=False,
        optimize=True,
        lossless=False,
    ),
    Preset.FORM_PHOTO: PresetParams(
        quality=82,
        allow_resize=True,
        max_dimension=800,
        progressive=True,
        optimize=True,
        lossless=False,
        preferred_format="JPEG",
    ),
    Preset.TRANSPARENT: PresetParams(
        quality=85,
        allow_resize=False,
        max_dimension=0,
        progressive=False,
        optimize=True,
        lossless=False,
        preferred_format="PNG",
    ),
}
