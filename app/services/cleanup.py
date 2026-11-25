"""
app/services/cleanup.py

Temporary file cleanup utilities.
Cleans up per-session temp files and orphaned files at startup.
"""
from __future__ import annotations

import glob
import logging
import os
import tempfile
import time

logger = logging.getLogger(__name__)

# Prefix used for all temp files produced by this bot
TEMP_PREFIX = "kayicomp_"


def cleanup_session_files(*paths: str) -> None:
    """Delete specific temp files. Silently ignores missing files."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                logger.debug("Could not remove temp file %s: %s", path, e)


def cleanup_orphaned_files(max_age_seconds: int = 3600) -> int:
    """
    Remove orphaned temp files older than max_age_seconds from the system temp dir.
    Returns the number of files removed.
    """
    tmp_dir = tempfile.gettempdir()
    pattern = os.path.join(tmp_dir, f"{TEMP_PREFIX}*")
    removed = 0
    for path in glob.glob(pattern):
        try:
            age = time.time() - os.path.getmtime(path)
            if age > max_age_seconds:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info("Startup cleanup: removed %d orphaned temp files.", removed)
    return removed


def get_temp_storage_usage() -> tuple[int, int]:
    """
    On-demand calculation of current temporary storage used by kayicomp_* files.
    Returns (total_bytes, file_count).
    """
    tmp_dir = tempfile.gettempdir()
    pattern = os.path.join(tmp_dir, f"{TEMP_PREFIX}*")
    total_size = 0
    count = 0
    for path in glob.glob(pattern):
        try:
            total_size += os.path.getsize(path)
            count += 1
        except OSError:
            pass
    return total_size, count


def enforce_storage_budget(max_bytes: int = 50 * 1024 * 1024) -> int:
    """
    Enforce global disk storage budget for temporary files.
    If total size of kayicomp_* files exceeds max_bytes, prunes oldest files
    until usage drops below 80% of max_bytes.
    Returns count of pruned files.
    """
    tmp_dir = tempfile.gettempdir()
    pattern = os.path.join(tmp_dir, f"{TEMP_PREFIX}*")
    file_list = []
    total_size = 0

    for path in glob.glob(pattern):
        try:
            st = os.stat(path)
            file_list.append((path, st.st_size, st.st_mtime))
            total_size += st.st_size
        except OSError:
            pass

    if total_size <= max_bytes:
        return 0

    # Sort oldest first
    file_list.sort(key=lambda x: x[2])
    target_size = int(max_bytes * 0.8)
    pruned = 0

    for path, size, _ in file_list:
        try:
            os.remove(path)
            total_size -= size
            pruned += 1
            if total_size <= target_size:
                break
        except OSError:
            pass

    if pruned:
        logger.warning(
            "Storage budget exceeded! Pruned %d oldest temp files, current total: %.1f MB",
            pruned, total_size / (1024 * 1024)
        )
    return pruned


def make_temp_path(extension: str = "jpg", max_budget_bytes: int = 50 * 1024 * 1024) -> str:
    """
    Create a unique temp file path (file is NOT created).
    Caller is responsible for writing and deleting the file.
    Also ensures storage budget is enforced before new files accumulate.
    """
    import uuid
    enforce_storage_budget(max_budget_bytes)
    return os.path.join(tempfile.gettempdir(), f"{TEMP_PREFIX}{uuid.uuid4().hex}.{extension}")
