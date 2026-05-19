"""Registry of in-flight asyncio tasks for execution-agent runs.

Lets the interaction agent (or an admin endpoint) cancel a running
execution by request_id. Without this, fire-and-forget tasks created in
`server.agents.interaction_agent.tools._record_and_submit_execution`
would have no handle for cancellation.

Each registered task also has a paired asyncio.Queue inbox (Tier 4) that
the execution-agent loop drains between iterations, enabling
non-destructive interventions like adding constraints or clarifications
to an already-running task.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from ...logging_config import logger


@dataclass
class _Entry:
    task: asyncio.Task[object]
    inbox: asyncio.Queue[str] = field(default_factory=asyncio.Queue)


class TaskRegistry:
    """Thread-safe registry of in-flight execution tasks keyed by request_id."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock: threading.Lock = threading.Lock()

    def register(self, request_id: str, task: asyncio.Task[object]) -> None:
        """Add a task. Auto-removes itself when done."""
        with self._lock:
            self._entries[request_id] = _Entry(task=task)
        task.add_done_callback(lambda _t, rid=request_id: self._discard(rid))

    def _discard(self, request_id: str) -> None:
        with self._lock:
            _ = self._entries.pop(request_id, None)

    def cancel(self, request_id: str) -> bool:
        """Request cancellation of the task for `request_id`.

        Returns True iff a live task was found and `.cancel()` was called.
        Returns False for unknown ids and already-completed tasks.
        """
        with self._lock:
            entry = self._entries.get(request_id)
        if entry is None:
            logger.debug("cancel: unknown request_id", extra={"request_id": request_id})
            return False
        if entry.task.done():
            logger.debug("cancel: task already done", extra={"request_id": request_id})
            return False
        cancelled = entry.task.cancel()
        logger.info(
            "cancel: requested",
            extra={"request_id": request_id, "cancelled": cancelled},
        )
        return cancelled

    def has(self, request_id: str) -> bool:
        with self._lock:
            return request_id in self._entries

    def active_request_ids(self) -> list[str]:
        with self._lock:
            return [rid for rid, e in self._entries.items() if not e.task.done()]

    # ---- Inbox (Tier 4 — soft intervention) ---------------------------------

    def push_followup(self, request_id: str, message: str) -> bool:
        """Enqueue a follow-up message for the running agent. Returns False
        if no such task is registered (unknown or already finished)."""
        with self._lock:
            entry = self._entries.get(request_id)
        if entry is None or entry.task.done():
            return False
        try:
            entry.inbox.put_nowait(message)
        except asyncio.QueueFull:  # pragma: no cover - bounded later if needed
            logger.warning(
                "followup queue full",
                extra={"request_id": request_id},
            )
            return False
        logger.info(
            "followup: queued",
            extra={"request_id": request_id, "chars": len(message)},
        )
        return True

    def drain_inbox(self, request_id: str) -> list[str]:
        """Pull all pending follow-ups for a running agent. Safe to call
        even when no entry exists (returns []) — supports the drain-at-
        iteration-boundary pattern without forcing the caller to gate."""
        with self._lock:
            entry = self._entries.get(request_id)
        if entry is None:
            return []
        messages: list[str] = []
        while not entry.inbox.empty():
            try:
                messages.append(entry.inbox.get_nowait())
            except asyncio.QueueEmpty:  # pragma: no cover - race-safe exit
                break
        return messages


_registry = TaskRegistry()


def get_task_registry() -> TaskRegistry:
    return _registry


__all__ = ["TaskRegistry", "get_task_registry"]
