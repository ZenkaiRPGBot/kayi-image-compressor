"""
app/compression/presets.py

Compression preset definitions and CompressionRequest dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Preset(str, Enum):
    BEST_QUALITY = "best_quality"
    BALANCED = "balanced"
    SMALLEST = "smallest"
    LOSSLESS = "lossless"


@dataclass
class CompressionRequest:
    """All parameters for a single compression job."""
    input_path: str
    output_path: str

    # Compression mode — either preset OR target_bytes (not both)
    preset: Optional[Preset] = None
    target_bytes: Optional[int] = None

    # Output format: "JPEG", "PNG", "WEBP", or "" to keep original
    output_format: str = ""

    # Resize constraints (0 = no limit)
    max_width: int = 0
    max_height: int = 0
    allow_resize: bool = False

    # Metadata
    strip_metadata: bool = True
    keep_aspect_ratio: bool = True

    # Lossless mode (overrides quality)
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
}
