"""
tests/test_worker_timeout.py

Tests for hard timeout enforcement, process termination, and recovery.
Demonstrates that CPU-bound / hanging work actually terminates and subsequent jobs succeed.
"""
import asyncio
import os
import time
import pytest
from app.compression.presets import CompressionRequest, Preset
from app.compression.engine import run_compression_isolated


@pytest.mark.asyncio
async def test_worker_timeout_terminates_and_recovers(tmp_jpeg, tmp_path, monkeypatch):
    """
    Simulates a hanging/long-running compression task.
    Verifies that run_compression_isolated terminates the worker and subsequent jobs run cleanly.
    """
    out1 = str(tmp_path / "timeout_out.jpg")
    req_slow = CompressionRequest(
        input_path=tmp_jpeg,
        output_path=out1,
        preset=Preset.BALANCED,
    )

    # Set test environment flag passed to spawned worker process
    monkeypatch.setenv("_TEST_SIMULATE_SLOW_WORKER", "1")

    # 1. Run with 1 second timeout — must raise TimeoutError
    t0 = time.time()
    with pytest.raises(asyncio.TimeoutError):
        await run_compression_isolated(req_slow, timeout_seconds=1.0)
    elapsed = time.time() - t0

    # Ensure it terminated promptly around 1-3s, not waiting 10s!
    assert elapsed < 4.0

    # 2. Restore normal compression and verify subsequent job succeeds!
    monkeypatch.delenv("_TEST_SIMULATE_SLOW_WORKER", raising=False)

    out2 = str(tmp_path / "recovered_out.jpg")
    req_normal = CompressionRequest(
        input_path=tmp_jpeg,
        output_path=out2,
        preset=Preset.BALANCED,
    )
    res = await run_compression_isolated(req_normal, timeout_seconds=10.0)
    assert res.success
    assert os.path.exists(out2)
