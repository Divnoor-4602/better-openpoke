from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..config import Settings, get_settings
from ..core.workspace_context import set_current_workspace
from ..db.workspace_registry import get_workspace_registry

_HANDLE_MAX_LEN = 64
_HANDLE_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789_")

_security = HTTPBasic(auto_error=True)


def _normalize_handle(raw: str) -> str:
    handle = raw.strip().lower()
    if not handle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="handle must not be empty",
        )
    if len(handle) > _HANDLE_MAX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"handle must be at most {_HANDLE_MAX_LEN} characters",
        )
    if any(c not in _HANDLE_ALLOWED for c in handle):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="handle must contain only lowercase letters, digits, and underscores",
        )
    return handle


def _client_ip(request: Request) -> str | None:
    """Pick the most-trustworthy client IP we can see.

    Behind a proxy (Railway, etc.) `request.client.host` is the proxy
    address; the original client lives in `X-Forwarded-For`. We honor
    the first XFF entry when present, otherwise fall back to the direct
    peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else None


async def get_workspace_id(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials, Depends(_security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Validate demo Basic auth and return the caller's workspace id.

    Side effect: binds the workspace id into the request's ContextVar so
    tool helpers can read it via
    `workspace_context.get_current_workspace()`.

    This function is declared async so FastAPI runs it in the request's
    asyncio task (sync deps run in a threadpool with a separate
    ContextVar copy, which would prevent the binding from propagating
    to the route handler).
    """

    expected = (settings.demo_password or "").encode("utf-8")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEMO_PASSWORD is not configured on the server",
        )

    provided = (credentials.password or "").encode("utf-8")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    workspace_id = _normalize_handle(credentials.username or "")
    set_current_workspace(workspace_id)

    # Observability: first-IP-wins record. Doesn't reject duplicates;
    # logs a warning when a second IP shows up for the same handle.
    try:
        get_workspace_registry().register(workspace_id, _client_ip(request))
    except Exception:  # pragma: no cover - registry is best-effort
        pass

    return workspace_id
