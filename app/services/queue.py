"""
app/services/queue.py

Bounded asyncio job queue for compression requests.
Rejects new jobs gracefully when at capacity.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional


@dataclass
class QueueJob:
    job_id: str
    user_id: int
    coro: Any  # Coroutine to execute


class JobQueue:
    """
    Bounded asyncio job queue with a single worker.

    max_size: Maximum number of queued jobs (not counting the running one)
    When the queue is full, new jobs are rejected immediately.
    """

    def __init__(self, max_size: int = 5) -> None:
        self._max_size = max_size
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background worker. Call once at startup."""
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Drain and stop the worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, job: QueueJob) -> bool:
        """
        Try to add a job to the queue.
        Returns True if accepted, False if queue is full.
        """
        try:
            self._queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            return False

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_full(self) -> bool:
        return self._queue.full()

    async def _worker(self) -> None:
        while self._running:
            try:
                job: QueueJob = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                try:
                    await job.coro
                except Exception as e:
                    pass  # Individual job errors are handled inside the coro
                finally:
                    self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
