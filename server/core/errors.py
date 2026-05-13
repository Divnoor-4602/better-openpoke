from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..logging_config import logger
from .request_id import get_request_id


class ErrorResponse(BaseModel):
    ok: bool = Field(default=False)
    error: str
    detail: Any | None = None
    requestId: str


def error_payload(request: Request, error: str, detail: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    detail: Any | None = None,
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
        logger.debug(
            "validation error",
            extra={"errors": exc.errors(), "path": request.url.path},
        )
        return error_response(
            request,
            "Invalid request",
            detail=exc.errors(),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    _ = _validation_exception_handler

    @fastapi_app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        logger.debug(
            "http error",
            extra={
                "detail": exc.detail,
                "status": exc.status_code,
                "path": request.url.path,
            },
        )
        detail = exc.detail
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


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
}

