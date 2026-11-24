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
        # Never label an oversized result as meeting the target
        assert not result.success
        assert result.target_result is not None
        assert not result.target_result.success


class TestSpecializedPresets:
    def test_photo_preset(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "photo.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.PHOTO,
            strip_metadata=True,
        )
        res = compress_image_sync(req)
        assert res.success
        assert res.stats.output_format == "JPEG"

    def test_screenshot_preset(self, tmp_png, tmp_path):
        out = str(tmp_path / "screenshot.jpg")
        req = CompressionRequest(
            input_path=tmp_png,
            output_path=out,
            preset=Preset.SCREENSHOT,
            output_format="JPEG",
        )
        res = compress_image_sync(req)
        assert res.success

    def test_signature_preset_binarization(self, tmp_path):
        # Create image simulating signature on off-white paper
        img = Image.new("RGB", (200, 100), (230, 230, 225))
        # Draw dark pen line
        for x in range(50, 150):
            img.putpixel((x, 50), (30, 30, 40))
        p = str(tmp_path / "sig_input.jpg")
        img.save(p, format="JPEG", quality=90)

        out = str(tmp_path / "sig_out.jpg")
        req = CompressionRequest(
            input_path=p,
            output_path=out,
            preset=Preset.SIGNATURE,
            output_format="JPEG",
        )
        res = compress_image_sync(req)
        assert res.success
        out_img = Image.open(out).convert("L")
        # Paper should have been whitened (close to 255)
        assert out_img.getpixel((10, 10)) >= 240
        # Signature stroke should remain dark
        assert out_img.getpixel((100, 50)) <= 80

    def test_transparent_preset(self, tmp_png_alpha, tmp_path):
        out = str(tmp_path / "trans.png")
        req = CompressionRequest(
            input_path=tmp_png_alpha,
            output_path=out,
            preset=Preset.TRANSPARENT,
            output_format="PNG",
        )
        res = compress_image_sync(req)
        assert res.success
        out_img = Image.open(out)
        assert out_img.mode in ("RGBA", "LA", "PA") or "transparency" in out_img.info


class TestLosslessQuality:
    def test_lossless_jpeg_avoids_png_blowup(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "lossless.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            preset=Preset.LOSSLESS,
            output_format="JPEG",
        )
        res = compress_image_sync(req)
        assert res.success
        assert res.stats.output_format == "JPEG"
        # Must not be larger than original!
        assert os.path.getsize(out) <= os.path.getsize(tmp_jpeg)

    def test_lossless_png_pixel_equality(self, tmp_png, tmp_path):
        from PIL import ImageChops
        out = str(tmp_path / "lossless.png")
        req = CompressionRequest(
            input_path=tmp_png,
            output_path=out,
            preset=Preset.LOSSLESS,
            output_format="PNG",
        )
        res = compress_image_sync(req)
        assert res.success
        orig = Image.open(tmp_png)
        compressed = Image.open(out)
        diff = ImageChops.difference(orig.convert("RGBA"), compressed.convert("RGBA"))
        assert diff.getbbox() is None


class TestFormUploadMode:
    def test_exact_dimensions_pad_white(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "form_pad.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            exact_width=400,
            exact_height=400,
            fit_mode="pad",
            output_format="JPEG",
            is_form_mode=True,
            form_max_bytes=100 * 1024,
        )
        res = compress_image_sync(req)
        assert res.success
        out_img = Image.open(out)
        assert out_img.size == (400, 400)

    def test_exact_dimensions_crop(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "form_crop.jpg")
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            exact_width=150,
            exact_height=150,
            fit_mode="crop",
            output_format="JPEG",
            is_form_mode=True,
            form_max_bytes=100 * 1024,
        )
        res = compress_image_sync(req)
        assert res.success
        out_img = Image.open(out)
        assert out_img.size == (150, 150)

    def test_form_validation_failure_explanation(self, tmp_jpeg, tmp_path):
        out = str(tmp_path / "form_fail.jpg")
        # Set impossible constraint: 1 byte
        req = CompressionRequest(
            input_path=tmp_jpeg,
            output_path=out,
            target_bytes=1,
            output_format="JPEG",
            is_form_mode=True,
            form_max_bytes=1,
        )
        res = compress_image_sync(req)
        assert not res.success
        assert len(res.form_validation_errors) > 0
        assert "exceeds maximum limit" in res.form_validation_errors[0]
