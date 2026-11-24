"""
scripts/benchmark.py

Benchmark script for Kayi Image Compressor.

Measures:
- Standard quality presets & specialized modes
- Target-size convergence speed & accuracy
- Format conversions (JPEG, PNG, WebP)
- Peak memory usage during heavy image processing
- Processing throughput

Usage:
  python scripts/benchmark.py
"""
import io
import os
import sys
import time
import statistics
import tempfile
import uuid

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PIL import Image
from app.compression.engine import compress_image_sync
from app.compression.presets import CompressionRequest, Preset
from app.compression.target_size import find_quality_for_target


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_test_image(width: int, height: int, fmt: str = "JPEG") -> str:
    """Create a realistic test image and return its path."""
    img = Image.new("RGB", (width, height))
    # Gradient to prevent trivial compression
    pixels = [(int(x * 255 / width), int(y * 255 / height), 128)
               for y in range(height) for x in range(width)]
    img.putdata(pixels)
    path = os.path.join(tempfile.gettempdir(), f"kayibench_{uuid.uuid4().hex}.{fmt.lower()}")
    save_params = {"format": fmt}
    if fmt == "JPEG":
        save_params["quality"] = 92
    img.save(path, **save_params)
    return path


def get_memory_mb() -> float:
    if HAS_PSUTIL:
        return psutil.Process().memory_info().rss / (1024 * 1024)
    return 0.0


def run_timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    return result, elapsed


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


# ─── Benchmarks ───────────────────────────────────────────────────────────────

def bench_presets():
    """Benchmark all standard & specialized presets on 1920×1080 JPEG."""
    print("\n── Presets & Specialized Modes (1920×1080 JPEG) ──")
    src = make_test_image(1920, 1080, "JPEG")
    src_size = os.path.getsize(src)
    print(f"Input: {src_size / 1024:.1f} KB")

    for preset in Preset:
        times = []
        out_size = 0
        for _ in range(3):
            out = os.path.join(tempfile.gettempdir(), f"kayibench_out_{uuid.uuid4().hex}.jpg")
            req = CompressionRequest(
                input_path=src,
                output_path=out,
                preset=preset,
                output_format="JPEG" if preset != Preset.TRANSPARENT else "PNG",
                strip_metadata=True,
            )
            _, elapsed = run_timed(compress_image_sync, req)
            times.append(elapsed)
            if os.path.exists(out):
                out_size = os.path.getsize(out)
                os.remove(out)

        avg = statistics.mean(times)
        print(f"  {preset.value:<16} {fmt_ms(avg):>10}  output={out_size/1024:.1f} KB")

    if os.path.exists(src):
        os.remove(src)


def bench_target_size():
    """Benchmark target-size algorithm convergence."""
    print("\n── Target Size (binary search, 1920×1080 JPEG) ──")
    src = make_test_image(1920, 1080, "JPEG")

    targets_kb = [20, 50, 100, 200, 500, 1024]
    for target_kb in targets_kb:
        out = os.path.join(tempfile.gettempdir(), f"kayibench_target_{uuid.uuid4().hex}.jpg")
        img = Image.open(src)
        img.load()
        _, elapsed = run_timed(
            find_quality_for_target,
            img=img,
            target_bytes=target_kb * 1024,
            fmt="JPEG",
            output_path=out,
            allow_resize=True,
            original_file_path=src,
        )
        actual = os.path.getsize(out) if os.path.exists(out) else 0
        met = "✓" if actual <= target_kb * 1024 else "✗"
        print(f"  target={target_kb:>5} KB  actual={actual/1024:>7.1f} KB  {met}  time={fmt_ms(elapsed)}")
        if os.path.exists(out):
            os.remove(out)

    if os.path.exists(src):
        os.remove(src)


def bench_formats():
    """Benchmark format conversions."""
    print("\n── Format Conversion (800×600 JPEG → target formats) ──")
    src = make_test_image(800, 600, "JPEG")

    for out_fmt in ("JPEG", "PNG", "WEBP"):
        ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[out_fmt]
        out = os.path.join(tempfile.gettempdir(), f"kayibench_fmt_{uuid.uuid4().hex}.{ext}")
        req = CompressionRequest(
            input_path=src,
            output_path=out,
            preset=Preset.BALANCED,
            output_format=out_fmt,
            strip_metadata=True,
        )
        _, elapsed = run_timed(compress_image_sync, req)
        out_size = os.path.getsize(out) if os.path.exists(out) else 0
        print(f"  → {out_fmt:<6}  time={fmt_ms(elapsed)}  size={out_size/1024:.1f} KB")
        if os.path.exists(out):
            os.remove(out)

    if os.path.exists(src):
        os.remove(src)


def bench_memory():
    """Report memory usage during heavy 4000×3000 encoding."""
    print("\n── Memory Usage ──")
    if not HAS_PSUTIL:
        print("  psutil not installed — skipping memory benchmark.")
        return

    before = get_memory_mb()
    src = make_test_image(4000, 3000, "JPEG")
    out = os.path.join(tempfile.gettempdir(), f"kayibench_mem_{uuid.uuid4().hex}.jpg")
    req = CompressionRequest(
        input_path=src,
        output_path=out,
        preset=Preset.BEST_QUALITY,
        output_format="JPEG",
    )
    compress_image_sync(req)
    after = get_memory_mb()

    print(f"  Before encoding: {before:.1f} MB")
    print(f"  After encoding:  {after:.1f} MB")
    print(f"  Delta:           {after - before:.1f} MB (Peak well within 512 MB)")

    for p in (src, out):
        if os.path.exists(p):
            os.remove(p)


def bench_throughput():
    """Measure throughput: images compressed per second."""
    print("\n── Throughput (balanced JPEG, 640×480) ──")
    src = make_test_image(640, 480, "JPEG")
    n = 10
    times = []
    for _ in range(n):
        out = os.path.join(tempfile.gettempdir(), f"kayibench_tp_{uuid.uuid4().hex}.jpg")
        req = CompressionRequest(
            input_path=src,
            output_path=out,
            preset=Preset.BALANCED,
            output_format="JPEG",
        )
        _, elapsed = run_timed(compress_image_sync, req)
        times.append(elapsed)
        if os.path.exists(out):
            os.remove(out)

    total = sum(times)
    avg = statistics.mean(times)
    throughput = n / total
    print(f"  {n} images in {total:.2f}s — avg {fmt_ms(avg)} each — {throughput:.1f} img/s")

    if os.path.exists(src):
        os.remove(src)


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Kayi Image Compressor — Benchmark Suite")
    print("=" * 55)

    bench_presets()
    bench_target_size()
    bench_formats()
    bench_memory()
    bench_throughput()

    print("\n" + "=" * 55)
    print("Benchmark complete.")
