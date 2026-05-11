"""Summarization service package."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "get_working_memory_log": (".working_memory_log", "get_working_memory_log"),
    "schedule_summarization": (".scheduler", "schedule_summarization"),
    "SummaryState": (".state", "SummaryState"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    return getattr(module, attr_name)

__all__ = [
    "get_working_memory_log",
    "schedule_summarization",
    "SummaryState",
]
