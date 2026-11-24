"""
tests/test_queue.py

Tests for the bounded asyncio job queue.
"""
import asyncio
import pytest

from app.services.queue import JobQueue, QueueJob


class TestJobQueue:
    def test_enqueue_and_process(self):
        async def run():
            queue = JobQueue(max_size=5)
            results = []

            async def job_coro():
                results.append(1)

            await queue.start()
            job = QueueJob(job_id="j1", user_id=1, coro=job_coro())
            accepted = await queue.enqueue(job)
            assert accepted
            await asyncio.sleep(0.1)
            await queue.stop()
            assert 1 in results

        asyncio.run(run())

    def test_queue_full_rejects(self):
        async def run():
            queue = JobQueue(max_size=2)
            coros = []

            async def noop():
                await asyncio.sleep(10)

            # Fill the queue
            for i in range(2):
                c = noop()
                coros.append(c)
                job = QueueJob(job_id=f"j{i}", user_id=i, coro=c)
                await queue.enqueue(job)

            # This one should be rejected
            overflow_c = noop()
            coros.append(overflow_c)
            job = QueueJob(job_id="overflow", user_id=99, coro=overflow_c)
            accepted = await queue.enqueue(job)
            assert not accepted

            for c in coros:
                c.close()

        asyncio.run(run())

    def test_queue_size(self):
        async def run():
            queue = JobQueue(max_size=5)
            coros = []

            async def noop():
                pass

            for i in range(3):
                c = noop()
                coros.append(c)
                job = QueueJob(job_id=f"j{i}", user_id=i, coro=c)
                await queue.enqueue(job)

            assert queue.size == 3

            for c in coros:
                c.close()

        asyncio.run(run())
