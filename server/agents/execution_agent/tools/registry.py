"""Aggregate execution agent tool schemas and registries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import gmail, triggers
from ..tasks import get_task_registry, get_task_schemas


# Return OpenAI/OpenRouter-compatible tool schemas
def get_tool_schemas() -> list[dict[str, Any]]:
    """Return OpenAI/OpenRouter-compatible tool schemas."""

    return [
        *gmail.get_schemas(),
        *get_task_schemas(),
        *triggers.get_schemas(),
    ]


# Return Python callables for executing tools by name
def get_tool_registry(agent_name: str) -> dict[str, Callable[..., object]]:
    """Return Python callables for executing tools by name."""

    registry: dict[str, Callable[..., object]] = {}
    registry.update(gmail.build_registry(agent_name))
    registry.update(get_task_registry(agent_name))
    registry.update(triggers.build_registry(agent_name))
    return registry


__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
