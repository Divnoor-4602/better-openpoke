from __future__ import annotations

from contextvars import ContextVar

_current_workspace: ContextVar[str | None] = ContextVar(
    "openpoke_current_workspace", default=None
)


def set_current_workspace(workspace_id: str) -> None:
    _ = _current_workspace.set(workspace_id)


def get_current_workspace() -> str | None:
    return _current_workspace.get()


def require_current_workspace() -> str:
    value = _current_workspace.get()
    if not value:
        raise RuntimeError(
            "No workspace bound to the current execution context. Ensure the request handler depends on get_workspace_id, or call set_current_workspace explicitly in background tasks."
        )
    return value
