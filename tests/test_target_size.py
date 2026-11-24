"""
tests/test_target_size.py

Focused tests for the target-size adaptive algorithm.
Includes reproduction and verification tests for 2 MB images hitting 20 KB targets.
"""
import io
import os
import pytest
from PIL import Image, ImageDraw

from app.compression.target_size import find_quality_for_target


def make_jpeg_path(tmp_path, width=300, height=200):
    img = Image.new("RGB", (width, height), color=(80, 160, 200))
    p = str(tmp_path / "input.jpg")
    img.save(p, format="JPEG", quality=90)
    return p


def make_large_detailed_photo(tmp_path, width=3000, height=2000):
    """Generates a realistic detailed ~2.4 MB photo with geometric frequency patterns."""
    img = Image.new("RGB", (width, height), (120, 150, 180))
    draw = ImageDraw.Draw(img)
    for i in range(0, width, 20):
        draw.line([(i, 0), (width - i, height)], fill=((i * 3) % 255, (i * 7) % 255, (i * 11) % 255), width=2)
    for j in range(0, height, 20):
        draw.line([(0, j), (width, height - j)], fill=((j * 5) % 255, (j * 9) % 255, (j * 13) % 255), width=2)
    p = str(tmp_path / "large_photo.jpg")
    img.save(p, format="JPEG", quality=90)
    return p


class TestTargetSizeAlgorithm:
    def test_hits_reasonable_target(self, tmp_path):
        src = make_jpeg_path(tmp_path, 300, 200)
        out = str(tmp_path / "out.jpg")
        result = find_quality_for_target(
            img=Image.open(src),
            target_bytes=20 * 1024,
            fmt="JPEG",
            output_path=out,
            allow_resize=True,
        )
        assert os.path.exists(out)
        assert result.actual_bytes > 0
        assert result.actual_bytes <= 20 * 1024
        assert result.success is True

    def test_2mb_photo_compresses_to_20kb(self, tmp_path):
        """Verifies fix for user issue: 2.4 MB photo compressed to 20 KB target."""
        src = make_large_detailed_photo(tmp_path)
        assert os.path.getsize(src) > 1.5 * 1024 * 1024  # > 1.5 MB

        out = str(tmp_path / "out_20k.jpg")
        result = find_quality_for_target(
            img=Image.open(src),
            target_bytes=20 * 1024,
            fmt="JPEG",
            output_path=out,
            allow_resize=True,
        )
        assert os.path.exists(out)
        assert result.success is True
        assert result.actual_bytes <= 20 * 1024
        assert os.path.getsize(out) == result.actual_bytes

    def test_2mb_photo_compresses_to_50kb_and_100kb(self, tmp_path):
        """Verifies targets 50 KB and 100 KB on 2.4 MB photo."""
        src = make_large_detailed_photo(tmp_path)
        img = Image.open(src)

        for target_kb in (50, 100):
            out = str(tmp_path / f"out_{target_kb}k.jpg")
            result = find_quality_for_target(
                img=img,
                target_bytes=target_kb * 1024,
                fmt="JPEG",
                output_path=out,
                allow_resize=True,
            )
            assert result.success is True
            assert result.actual_bytes <= target_kb * 1024
            assert os.path.getsize(out) == result.actual_bytes

    def test_2mb_photo_no_resize_fails_honestly(self, tmp_path):
        """When resizing is disallowed, an impossible small target reports failure honestly."""
        src = make_large_detailed_photo(tmp_path)
        out = str(tmp_path / "out_no_resize.jpg")
        result = find_quality_for_target(
            img=Image.open(src),
            target_bytes=20 * 1024,
            fmt="JPEG",
            output_path=out,
            allow_resize=False,
        )
        assert result.success is False
        assert result.actual_bytes > 20 * 1024
        assert "Enable downscaling" in result.reason

    def test_transparent_png_target_size(self, tmp_path):
        """Transparent PNG downscales adaptively to meet strict target."""
        img = Image.new("RGBA", (1500, 1500), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([100, 100, 1400, 1400], fill=(255, 80, 40, 200))
        out = str(tmp_path / "out_trans.png")

        result = find_quality_for_target(
            img=img,
            target_bytes=20 * 1024,
            fmt="PNG",
            output_path=out,
            allow_resize=True,
        )
        assert os.path.exists(out)
        assert result.success is True
        assert result.actual_bytes <= 20 * 1024

    def test_impossible_target_returns_failure_result(self, tmp_path):
        src = make_jpeg_path(tmp_path, 300, 200)
        out = str(tmp_path / "out.jpg")
        result = find_quality_for_target(
            img=Image.open(src),
            target_bytes=5,  # 5 bytes — impossible
            fmt="JPEG",
            output_path=out,
            allow_resize=True,
        )
        assert not result.success
        assert result.actual_bytes > 0
        assert os.path.exists(out)

    def test_png_target_always_produces_output(self, tmp_path):
        img = Image.new("RGBA", (200, 150), color=(90, 120, 200, 200))
        out = str(tmp_path / "out.png")
        result = find_quality_for_target(
            img=img,
            target_bytes=50 * 1024,
            fmt="PNG",
            output_path=out,
        )
        assert os.path.exists(out)
        assert result.actual_bytes > 0

    def test_webp_target(self, tmp_path):
        img = Image.new("RGB", (300, 200), color=(200, 90, 60))
        out = str(tmp_path / "out.webp")
        result = find_quality_for_target(
            img=img,
            target_bytes=10 * 1024,
            fmt="WEBP",
            output_path=out,
            allow_resize=True,
        )
        assert os.path.exists(out)
        assert result.actual_bytes > 0
        assert result.actual_bytes <= 10 * 1024

    def test_quality_used_is_in_range(self, tmp_path):
        src = make_jpeg_path(tmp_path)
        out = str(tmp_path / "out.jpg")
        result = find_quality_for_target(
            img=Image.open(src),
            target_bytes=8 * 1024,
            fmt="JPEG",
            output_path=out,
        )
        if result.quality_used is not None:
            assert 1 <= result.quality_used <= 95
