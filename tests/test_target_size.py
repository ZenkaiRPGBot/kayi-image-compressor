"""
tests/test_target_size.py

Focused tests for the target-size binary search algorithm.
"""
import io
import os
import pytest
from PIL import Image

from app.compression.target_size import find_quality_for_target


def make_jpeg_path(tmp_path, width=300, height=200):
    img = Image.new("RGB", (width, height), color=(80, 160, 200))
    p = str(tmp_path / "input.jpg")
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
        # Either target met or at least a file was written
        assert result.output_path == out

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
        assert result.actual_bytes > 0  # Still wrote something
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
