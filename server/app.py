from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .logging_config import configure_logging, logger
from .routes import api_router
from .services.gmail.importance_watcher import get_important_email_watcher
from .services.memory.worker import get_memory_index_worker
from .services.trigger_scheduler import get_trigger_scheduler


# Register global exception handlers for consistent error responses across the API
def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.debug(
            "validation error", extra={"errors": exc.errors(), "path": str(request.url)}
        )
        return JSONResponse(
            {"ok": False, "error": "Invalid request", "detail": exc.errors()},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    _ = _validation_exception_handler

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        logger.debug(
            "http error",
            extra={
                "detail": exc.detail,
                "status": exc.status_code,
                "path": str(request.url),
            },
        )
        raw_detail = cast(object, exc.detail)
        detail = raw_detail if isinstance(raw_detail, str) else json.dumps(raw_detail)
        return JSONResponse({"ok": False, "error": detail}, status_code=exc.status_code)

    _ = _http_exception_handler

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        _ = exc
        logger.exception("Unhandled error", extra={"path": str(request.url)})
        return JSONResponse(
            {"ok": False, "error": "Internal server error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    _ = _unhandled_exception_handler


configure_logging()
_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _ = app
    scheduler = get_trigger_scheduler()
    watcher = get_important_email_watcher()
    memory_index_worker = await get_memory_index_worker()
    await scheduler.start()
    await watcher.start()
    await memory_index_worker.start()
    try:
        yield
    finally:
        await memory_index_worker.stop()
        await scheduler.stop()
        await watcher.stop()


app = FastAPI(
    title=_settings.app_name,
    version=_settings.app_version,
    docs_url=_settings.resolved_docs_url,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)


__all__ = ["app"]
