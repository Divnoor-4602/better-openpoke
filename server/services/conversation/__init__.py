"""Conversation-related service helpers."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .log import ConversationLog, get_conversation_log
    from .summarization.scheduler import schedule_summarization
    from .summarization.state import SummaryState
    from .summarization.working_memory_log import get_working_memory_log

_EXPORTS: dict[str, tuple[str, str]] = {
    "ConversationLog": (".log", "ConversationLog"),
    "get_conversation_log": (".log", "get_conversation_log"),
    "SummaryState": (".summarization.state", "SummaryState"),
    "get_working_memory_log": (
        ".summarization.working_memory_log",
        "get_working_memory_log",
    ),
    "schedule_summarization": (".summarization.scheduler", "schedule_summarization"),
}


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    return cast(object, getattr(module, attr_name))

__all__ = [
    "ConversationLog",
    "get_conversation_log",
    "SummaryState",
    "get_working_memory_log",
    "schedule_summarization",
]
