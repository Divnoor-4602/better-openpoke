from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..logging_config import logger
from .request_id import get_request_id


class ErrorResponse(BaseModel):
    ok: bool = Field(default=False)
    error: str
    detail: object | None = None
    requestId: str


def error_payload(
    request: Request, error: str, detail: object | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": False,
        "error": error,
        "requestId": get_request_id(request),
    }
    if detail is not None:
        payload["detail"] = detail
    return payload


def error_response(
    request: Request,
    error: str,
    *,
    status_code: int,
    detail: object | None = None,
) -> JSONResponse:
    return JSONResponse(
        error_payload(request, error, detail),
        status_code=status_code,
    )


def register_exception_handlers(app: object) -> None:
    from fastapi import FastAPI

    fastapi_app = app if isinstance(app, FastAPI) else None
    if fastapi_app is None:  # pragma: no cover - defensive
        raise TypeError("register_exception_handlers requires a FastAPI app")

    @fastapi_app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized = _sanitize_validation_errors(exc.errors())
        logger.debug(
            "validation error",
            extra={"errors": sanitized, "path": request.url.path},
        )
        return error_response(
            request,
            "Invalid request",
            detail=sanitized,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    _ = _validation_exception_handler

    @fastapi_app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        # Starlette types `detail` as `str | None`, but FastAPI handlers raise
        # HTTPException with arbitrary JSON-shaped payloads in practice — so
        # narrow via object before the isinstance branches.
        detail: object = cast(object, exc.detail)
        logger.debug(
            "http error",
            extra={
                "detail": _redact_detail(detail),
                "status": exc.status_code,
                "path": request.url.path,
            },
        )
        message = detail if isinstance(detail, str) else "HTTP error"
        response_detail = None if isinstance(detail, str) else detail
        return error_response(
            request,
            message,
            detail=response_detail,
            status_code=exc.status_code,
        )

    _ = _http_exception_handler

    @fastapi_app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        _ = exc
        logger.exception("Unhandled error", extra={"path": request.url.path})
        return error_response(
            request,
            "Internal server error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    _ = _unhandled_exception_handler


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
}


def _sanitize_validation_errors(
    errors: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    sanitized_errors: list[dict[str, object]] = []
    for error in errors:
        sanitized: dict[str, object] = {
            key: value
            for key, value in error.items()
            if key not in {"input", "ctx"}
        }
        sanitized_errors.append(sanitized)
    return sanitized_errors


def _redact_detail(detail: object) -> object:
    if isinstance(detail, list):
        detail_list = cast(list[object], detail)
        items: list[object] = [_redact_detail(item) for item in detail_list]
        return {
            "type": "list",
            "count": len(detail_list),
            "items": items,
        }
    if isinstance(detail, dict):
        detail_dict = cast(dict[object, object], detail)
        return {
            key: _redact_detail(value)
            for key, value in detail_dict.items()
            if key not in {"input", "ctx"}
        }
    return {"type": type(detail).__name__}
