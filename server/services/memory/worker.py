"""Background memory indexing worker."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...config import get_settings
from ...logging_config import logger
from .indexer import MemoryIndexer, pinecone_enabled
from .store import _MEMORY_DB_PATH


class MemoryIndexWorker:
    """Runs Pinecone indexing outside request/agent business logic."""

    def __init__(self, db_path: Path = _MEMORY_DB_PATH) -> None:
        self._db_path = db_path
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._tasks:
                return
            settings = get_settings()
            if not pinecone_enabled():
                logger.info("Memory index worker disabled; Pinecone is not configured")
                return
            worker_count = max(1, settings.memory_index_workers)
            self._running = True
            loop = asyncio.get_running_loop()
            self._tasks = [
                loop.create_task(self._run(index), name=f"memory-index-worker-{index}")
                for index in range(worker_count)
            ]
            logger.info(
                "Memory index worker started",
                extra={
                    "workers": worker_count,
                    "batch_size": settings.memory_index_batch_size,
                    "transport": "sqlite_poll",
                    "poll_interval_seconds": settings.memory_index_poll_interval_seconds,
                },
            )

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            tasks = self._tasks
            self._tasks = []
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if tasks:
                logger.info("Memory index worker stopped")

    async def _run(self, worker_index: int) -> None:
        settings = get_settings()
        indexer = MemoryIndexer(self._db_path)
        try:
            while self._running:
                await asyncio.sleep(settings.memory_index_poll_interval_seconds)

                synced = await indexer.sync_pending_async(
                    limit=settings.memory_index_batch_size
                )
                if synced:
                    stats = indexer.queue_stats()
                    logger.info(
                        "Memory index worker synced records",
                        extra={
                            "worker": worker_index,
                            "synced": synced,
                            "queue": stats,
                        },
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive background loop
            logger.exception(
                "Memory index worker crashed",
                extra={"worker": worker_index, "error": str(exc)},
            )


_memory_index_worker: MemoryIndexWorker | None = None
_memory_index_worker_lock = asyncio.Lock()


async def get_memory_index_worker() -> MemoryIndexWorker:
    global _memory_index_worker
    if _memory_index_worker is None:
        async with _memory_index_worker_lock:
            if _memory_index_worker is None:
                _memory_index_worker = MemoryIndexWorker()
    return _memory_index_worker


__all__ = ["MemoryIndexWorker", "get_memory_index_worker"]
