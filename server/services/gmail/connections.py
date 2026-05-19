"""Tiny per-workspace registry of workspaces with Gmail connections.

The importance-email watcher reads this to know which workspaces to
poll. Maintained as a simple JSON set; `connect_google` / `disconnect_google`
update it.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import cast

from ...core.paths import get_data_dir
from ...logging_config import logger

_DATA_DIR = get_data_dir()
_REGISTRY_PATH = _DATA_DIR / "gmail_workspaces.json"

_lock = threading.Lock()


def _load() -> set[str]:
    try:
        raw = _REGISTRY_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "gmail workspace registry read failed", extra={"error": str(exc)}
        )
        return set()
    try:
        data = cast(object, json.loads(raw or "[]"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, list):
        items = cast(list[object], data)
        return {str(item) for item in items if item}
    return set()


def _save(workspaces: set[str]) -> None:
    try:
        _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ = _REGISTRY_PATH.write_text(
            json.dumps(sorted(workspaces)), encoding="utf-8"
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "gmail workspace registry write failed", extra={"error": str(exc)}
        )


def register_workspace(workspace_id: str) -> None:
    if not workspace_id:
        return
    with _lock:
        workspaces = _load()
        if workspace_id in workspaces:
            return
        workspaces.add(workspace_id)
        _save(workspaces)


def unregister_workspace(workspace_id: str) -> None:
    if not workspace_id:
        return
    with _lock:
        workspaces = _load()
        if workspace_id not in workspaces:
            return
        workspaces.discard(workspace_id)
        _save(workspaces)


def list_workspaces_with_gmail() -> list[str]:
    with _lock:
        return sorted(_load())


__all__ = [
    "register_workspace",
    "unregister_workspace",
    "list_workspaces_with_gmail",
]
