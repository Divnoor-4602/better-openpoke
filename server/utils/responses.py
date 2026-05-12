"""Response utilities."""

from __future__ import annotations

from fastapi.responses import JSONResponse


def error_response(message: str, *, status_code: int, detail: str | None = None) -> JSONResponse:
    """Create a standardized error response."""
    payload = {"ok": False, "error": message}
    if detail:
        payload["detail"] = detail
    return JSONResponse(payload, status_code=status_code)
