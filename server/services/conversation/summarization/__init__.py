"""Summarization service package."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .scheduler import schedule_summarization
    from .state import SummaryState
    from .working_memory_log import get_working_memory_log

_EXPORTS: dict[str, tuple[str, str]] = {
    "get_working_memory_log": (".working_memory_log", "get_working_memory_log"),
    "schedule_summarization": (".scheduler", "schedule_summarization"),
    "SummaryState": (".state", "SummaryState"),
}


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    return cast(object, getattr(module, attr_name))

__all__ = [
    "get_working_memory_log",
    "schedule_summarization",
    "SummaryState",
]
