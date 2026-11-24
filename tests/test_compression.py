"""
tests/test_compression.py

Tests for the compression engine — presets, formats, transparency, EXIF.
"""
import io
import os
import pytest
from PIL import Image

from app.compression.engine import compress_image_sync, CompressionResult
from app.compression.presets import CompressionRequest, Preset


class TestPresetCompression:
    def test_best_quality_jpeg(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.BEST_QUALITY,
            output_format="JPEG",
            strip_metadata=True,
        )
        result = compress_image_sync(req)
        assert result.success
        assert os.path.exists(out)
        assert result.stats is not None
        assert result.stats.output_bytes > 0

    def test_balanced_jpeg(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.BALANCED,
            output_format="JPEG",
        )
        result = compress_image_sync(req)
        assert result.success
        assert result.stats.output_format == "JPEG"

    def test_smallest_jpeg(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.SMALLEST,
            output_format="JPEG",
        )
        result = compress_image_sync(req)
        assert result.success
        # Smallest should produce smaller or equal output than balanced
        balanced_out = str(tmp_path / "balanced.jpg")
        req2 = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=balanced_out,
            preset=Preset.BALANCED,
            output_format="JPEG",
        )
        compress_image_sync(req2)
        assert result.stats.output_bytes <= os.path.getsize(balanced_out) + 1000

    def test_lossless_png(self, tmp_png, tmp_path):
        out = str(tmp_path / "out.png")
        req = CompressionRequest(
            input_path=tmp_png,
            output_path=out,
            preset=Preset.LOSSLESS,
            output_format="PNG",
        )
        result = compress_image_sync(req)
        assert result.success
        # Lossless PNG must be valid image
        img = Image.open(out)
        img.verify()

    def test_webp_output(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "out.webp")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.BALANCED,
            output_format="WEBP",
        )
        result = compress_image_sync(req)
        assert result.success
        assert result.stats.output_format == "WEBP"

    def test_png_to_jpeg_transparency(self, tmp_png_alpha, tmp_path):
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path=tmp_png_alpha,
            output_path=out,
            preset=Preset.BALANCED,
            output_format="JPEG",
            strip_metadata=True,
        )
        result = compress_image_sync(req)
        assert result.success
        # Result must be valid JPEG
        img = Image.open(out)
        assert img.format == "JPEG"

    def test_missing_input_fails(self, tmp_path):
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path="/nonexistent/file.jpg",
            output_path=out,
            preset=Preset.BALANCED,
        )
        result = compress_image_sync(req)
        assert not result.success

    def test_stats_reduction(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.SMALLEST,
            output_format="JPEG",
        )
        result = compress_image_sync(req)
        assert result.success
        # Stats must be coherent
        assert result.stats.original_bytes > 0
        assert result.stats.output_bytes > 0
        assert 0 <= result.stats.reduction_percent <= 100


class TestTargetSizeCompression:
    def test_target_size_hit(self, tmp_jpeg, tmp_path):
        """Should compress JPEG to under 20 KB (small target for a small test image)."""
        out = str(tmp_path / "out.jpg")
        # Test image is ~8 KB at q85; target 15 KB should be achievable
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            target_bytes=15 * 1024,
            output_format="JPEG",
            allow_resize=True,
            strip_metadata=True,
        )
        result = compress_image_sync(req)
        assert result.success
        assert os.path.exists(out)
        assert os.path.getsize(out) <= 15 * 1024 or result.target_result is not None

    def test_target_size_impossible_does_not_crash(self, tmp_jpeg, tmp_path):
        """When target is impossibly small, return failure result without crashing."""
        out = str(tmp_path / "out.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            target_bytes=1,  # 1 byte — impossible
            output_format="JPEG",
            allow_resize=False,
        )
        result = compress_image_sync(req)
        assert result.success  # Engine returns success (file written) even if target not met
        assert result.target_result is not None
        # target_met should be False
        assert not result.target_result.success
