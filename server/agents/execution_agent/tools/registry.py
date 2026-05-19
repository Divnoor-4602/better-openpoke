"""Aggregate execution agent tool schemas and registries."""

from __future__ import annotations

from collections.abc import Callable

from ..tasks import get_task_registry, get_task_schemas
from .calendar import build_registry as _calendar_build_registry
from .calendar import get_schemas as _calendar_get_schemas
from .gmail import build_registry as _gmail_build_registry
from .gmail import get_schemas as _gmail_get_schemas
from .triggers import build_registry as _triggers_build_registry
from .triggers import get_schemas as _triggers_get_schemas


# Return OpenAI/OpenRouter-compatible tool schemas
def get_tool_schemas() -> list[dict[str, object]]:
    """Return OpenAI/OpenRouter-compatible tool schemas."""

    return [
        *_gmail_get_schemas(),
        *_calendar_get_schemas(),
        *get_task_schemas(),
        *_triggers_get_schemas(),
    ]


# Return Python callables for executing tools by name
def get_tool_registry(agent_name: str) -> dict[str, Callable[..., object]]:
    """Return Python callables for executing tools by name."""

    registry: dict[str, Callable[..., object]] = {}
    registry.update(_gmail_build_registry(agent_name))
    registry.update(_calendar_build_registry(agent_name))
    registry.update(get_task_registry(agent_name))
    registry.update(_triggers_build_registry(agent_name))
    return registry


__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
