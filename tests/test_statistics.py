"""
tests/test_statistics.py

Tests for CompressionStats dataclass.
"""
import pytest
from app.compression.statistics import CompressionStats


class TestCompressionStats:
    def test_reduction_percent(self):
        s = CompressionStats(
            original_bytes=1000,
            output_bytes=750,
            output_format="JPEG",
            output_dimensions=(200, 150),
            original_dimensions=(200, 150),
        )
        assert s.space_saved == 250
        assert s.reduction_percent == 25.0

    def test_zero_reduction(self):
        s = CompressionStats(
            original_bytes=1000,
            output_bytes=1000,
            output_format="JPEG",
            output_dimensions=(200, 150),
            original_dimensions=(200, 150),
        )
        assert s.space_saved == 0
        assert s.reduction_percent == 0.0

    def test_grew(self):
        s = CompressionStats(
            original_bytes=1000,
            output_bytes=1200,
            output_format="PNG",
            output_dimensions=(200, 150),
            original_dimensions=(200, 150),
        )
        assert s.grew is True
        assert s.space_saved == 0  # Clamped at 0

    def test_zero_original_safe(self):
        s = CompressionStats(
            original_bytes=0,
            output_bytes=500,
            output_format="JPEG",
            output_dimensions=(100, 100),
            original_dimensions=(100, 100),
        )
        assert s.reduction_percent == 0.0

    def test_size_formatting_kb(self):
        s = CompressionStats(
            original_bytes=50_000,
            output_bytes=25_000,
            output_format="JPEG",
            output_dimensions=(200, 150),
            original_dimensions=(200, 150),
        )
        assert "KB" in s.original_size_str
        assert "KB" in s.output_size_str

    def test_size_formatting_mb(self):
        s = CompressionStats(
            original_bytes=5 * 1024 * 1024,
            output_bytes=2 * 1024 * 1024,
            output_format="JPEG",
            output_dimensions=(3000, 2000),
            original_dimensions=(3000, 2000),
        )
        assert "MB" in s.original_size_str

    def test_dimensions_str(self):
        s = CompressionStats(
            original_bytes=1000,
            output_bytes=800,
            output_format="JPEG",
            output_dimensions=(1920, 1080),
            original_dimensions=(1920, 1080),
        )
        assert s.dimensions_str == "1920×1080"

    def test_dimensions_changed(self):
        s = CompressionStats(
            original_bytes=1000,
            output_bytes=800,
            output_format="JPEG",
            output_dimensions=(960, 540),
            original_dimensions=(1920, 1080),
        )
        assert s.dimensions_changed is True
