"""Task registry for execution agents."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .search_email.schemas import get_schemas as _get_email_search_schemas
from .search_email.tool import build_registry as _build_email_search_registry


# Return tool schemas contributed by task modules
def get_task_schemas() -> list[dict[str, Any]]:
    """Return tool schemas contributed by task modules."""

    return [*_get_email_search_schemas()]


# Return executable task tools keyed by name
def get_task_registry(agent_name: str) -> dict[str, Callable[..., Any]]:
    """Return executable task tools keyed by name."""

    registry: dict[str, Callable[..., Any]] = {}
    registry.update(_build_email_search_registry(agent_name))
    return registry


__all__ = [
    "get_task_registry",
    "get_task_schemas",
]
