"""Execution agent tool package."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    if name in {"get_tool_registry", "get_tool_schemas"}:
        module = import_module(".registry", __name__)
        return getattr(module, name)
    raise AttributeError(name)

__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
