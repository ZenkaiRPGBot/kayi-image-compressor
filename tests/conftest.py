"""
tests/conftest.py

Shared fixtures for Kayi Image Compressor tests.
"""
import io
import os
import tempfile
import pytest
from PIL import Image


def make_test_jpeg(width: int = 200, height: int = 150, quality: int = 85) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 180, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_test_png(width: int = 200, height: int = 150, with_alpha: bool = False) -> bytes:
    mode = "RGBA" if with_alpha else "RGB"
    img = Image.new(mode, (width, height), color=(90, 120, 200, 128) if with_alpha else (90, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_test_webp(width: int = 200, height: int = 150) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 90, 120))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=80)
    return buf.getvalue()


@pytest.fixture
def tmp_jpeg(tmp_path):
    path = str(tmp_path / "test.jpg")
    with open(path, "wb") as f:
        f.write(make_test_jpeg())
    return path


@pytest.fixture
def tmp_png(tmp_path):
    path = str(tmp_path / "test.png")
    with open(path, "wb") as f:
        f.write(make_test_png())
    return path


@pytest.fixture
def tmp_png_alpha(tmp_path):
    path = str(tmp_path / "test_alpha.png")
    with open(path, "wb") as f:
        f.write(make_test_png(with_alpha=True))
    return path


@pytest.fixture
def tmp_webp(tmp_path):
    path = str(tmp_path / "test.webp")
    with open(path, "wb") as f:
        f.write(make_test_webp())
    return path


@pytest.fixture
def output_path(tmp_path):
    return str(tmp_path / "output.jpg")
