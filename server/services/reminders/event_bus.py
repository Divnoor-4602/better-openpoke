"""In-memory workspace-scoped pub/sub for reminder fire events.

Subscribers (SSE endpoints) call ``subscribe(workspace_id)`` to obtain an
asyncio queue. The trigger scheduler calls ``publish(workspace_id, event)``
when a reminder fires. Missed events (no subscriber) are dropped — the
durable record lives in the workspace conversation log.
"""

from __future__ import annotations

import asyncio
import threading
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from ...logging_config import logger


_QUEUE_MAXSIZE: int = 64


class ReminderEvent(BaseModel):
    """One reminder fire event delivered to the browser."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    trigger_id: int
    payload: str
    fired_at: str


class ReminderEventBus:
    """Per-workspace asyncio queue fan-out, in-process only."""

    _subs: dict[str, list[asyncio.Queue[ReminderEvent]]]
    _loops: dict[int, asyncio.AbstractEventLoop]
    _lock: threading.Lock

    def __init__(self) -> None:
        self._subs = {}
        self._loops = {}
        self._lock = threading.Lock()

    def subscribe(self, workspace_id: str) -> asyncio.Queue[ReminderEvent]:
        queue: asyncio.Queue[ReminderEvent] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subs.setdefault(workspace_id, []).append(queue)
            self._loops[id(queue)] = loop
        return queue

    def unsubscribe(
        self, workspace_id: str, queue: asyncio.Queue[ReminderEvent]
    ) -> None:
        with self._lock:
            queues = self._subs.get(workspace_id)
            if queues is None:
                return
            try:
                queues.remove(queue)
            except ValueError:
                pass
            if not queues:
                del self._subs[workspace_id]
            _ = self._loops.pop(id(queue), None)

    def publish(self, workspace_id: str, event: ReminderEvent) -> None:
        with self._lock:
            pairs = [
                (q, self._loops.get(id(q)))
                for q in self._subs.get(workspace_id, ())
            ]
        if not pairs:
            logger.info(
                "reminder fired with no active subscribers",
                extra={"workspace_id": workspace_id, "trigger_id": event.trigger_id},
            )
            return
        for queue, loop in pairs:
            if loop is None:
                continue
            _ = loop.call_soon_threadsafe(self._safe_enqueue, queue, event)

    @staticmethod
    def _safe_enqueue(
        queue: asyncio.Queue[ReminderEvent], event: ReminderEvent
    ) -> None:
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass
        try:
            _ = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug(
                "reminder subscriber queue full after eviction; dropping event",
                extra={"trigger_id": event.trigger_id},
            )


_bus_instance: ReminderEventBus | None = None


def get_reminder_event_bus() -> ReminderEventBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = ReminderEventBus()
    return _bus_instance


__all__ = ["ReminderEvent", "ReminderEventBus", "get_reminder_event_bus"]
