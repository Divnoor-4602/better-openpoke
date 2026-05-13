from __future__ import annotations

import asyncio
from importlib import import_module

from ....logging_config import logger

_pending = False
_running = False


def schedule_summarization() -> None:
    """Schedule a background summarization pass if not already queued."""
    global _pending
    _pending = True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("summarization skipped (no running event loop)")
        return

    if not _running:
        loop.create_task(_run_worker())


async def _run_worker() -> None:
    global _pending, _running
    if _running:
        return

    _running = True
    try:
        summarize_conversation = import_module(
            "server.services.conversation.summarization.summarizer"
        ).summarize_conversation
        while _pending:
            _pending = False
            try:
                await summarize_conversation()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "summarization worker failed",
                    extra={"error": str(exc)},
                )
    finally:
        _running = False


__all__ = ["schedule_summarization"]
