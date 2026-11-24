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


def make_temp_path(extension: str = "jpg") -> str:
    """
    Create a unique temp file path (file is NOT created).
    Caller is responsible for writing and deleting the file.
    """
    import uuid
    return os.path.join(tempfile.gettempdir(), f"{TEMP_PREFIX}{uuid.uuid4().hex}.{extension}")
