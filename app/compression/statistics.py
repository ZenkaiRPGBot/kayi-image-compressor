"""
app/compression/statistics.py

Result statistics dataclass with safe math and human-readable display.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class CompressionStats:
    original_bytes: int
    output_bytes: int
    output_format: str
    output_dimensions: Tuple[int, int]
    original_dimensions: Tuple[int, int]
    target_met: bool = False
    target_bytes: Optional[int] = None
    quality_used: Optional[int] = None

    @property
    def space_saved(self) -> int:
        return max(0, self.original_bytes - self.output_bytes)

    @property
    def reduction_percent(self) -> float:
        if self.original_bytes == 0:
            return 0.0
        return round((self.space_saved / self.original_bytes) * 100, 1)

    @property
    def grew(self) -> bool:
        """True if output is larger than input."""
        return self.output_bytes > self.original_bytes

    def _fmt_size(self, b: int) -> str:
        if b >= 1024 * 1024:
            return f"{b / (1024 * 1024):.2f} MB"
        return f"{b / 1024:.1f} KB"

    @property
    def original_size_str(self) -> str:
        return self._fmt_size(self.original_bytes)

    @property
    def output_size_str(self) -> str:
        return self._fmt_size(self.output_bytes)

    @property
    def saved_str(self) -> str:
        return self._fmt_size(self.space_saved)

    @property
    def dimensions_changed(self) -> bool:
        return self.original_dimensions != self.output_dimensions

    @property
    def dimensions_str(self) -> str:
        w, h = self.output_dimensions
        return f"{w}×{h}"
