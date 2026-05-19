from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import cast

from ....core.workspace_context import set_current_workspace
from ....logging_config import logger

_pending: set[str] = set()
_running: set[str] = set()
_lock = threading.Lock()


def schedule_summarization(workspace_id: str) -> None:
    """Schedule a per-workspace background summarization pass."""
    with _lock:
        _pending.add(workspace_id)
        already_running = workspace_id in _running

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug(
            "summarization skipped (no running event loop)",
            extra={"workspace_id": workspace_id},
        )
        return

    if not already_running:
        _ = loop.create_task(_run_worker(workspace_id))


async def _run_worker(workspace_id: str) -> None:
    with _lock:
        if workspace_id in _running:
            return
        _running.add(workspace_id)

    # Bind ContextVar so the summarizer's downstream calls (working memory
    # log, conversation log) resolve to this workspace's instances.
    set_current_workspace(workspace_id)
    try:
        summarize_conversation = cast(
            "Callable[[str], Awaitable[object]]",
            import_module(
                "server.services.conversation.summarization.summarizer"
            ).summarize_conversation,
        )
        while True:
            with _lock:
                if workspace_id not in _pending:
                    break
                _pending.discard(workspace_id)
            try:
                _ = await summarize_conversation(workspace_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "summarization worker failed",
                    extra={"error": str(exc), "workspace_id": workspace_id},
                )
    finally:
        with _lock:
            _running.discard(workspace_id)


def reset_workspace(workspace_id: str) -> None:
    """Drop in-memory scheduler state for a workspace (used by /dev/reset)."""
    with _lock:
        _pending.discard(workspace_id)
        _running.discard(workspace_id)


__all__ = ["schedule_summarization", "reset_workspace"]
