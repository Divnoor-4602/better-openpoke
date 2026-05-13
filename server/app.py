from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api_router
from .config import get_settings
from .core.errors import register_exception_handlers
from .core.openapi import install_custom_openapi
from .core.request_id import request_id_middleware
from .logging_config import configure_logging, logger
from .services.gmail.importance_watcher import get_important_email_watcher
from .services.memory.worker import get_memory_index_worker
from .services.trigger_scheduler import get_trigger_scheduler


configure_logging()
_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _ = app
    started_services: list[object] = []
    try:
        scheduler = get_trigger_scheduler()
        watcher = get_important_email_watcher()
        memory_index_worker = await get_memory_index_worker()
        for service in (scheduler, watcher, memory_index_worker):
            await service.start()
            started_services.append(service)
        yield
    finally:
        for service in reversed(started_services):
            try:
                await service.stop()
            except Exception as exc:  # pragma: no cover - defensive shutdown
                logger.warning(
                    "service shutdown failed",
                    extra={
                        "service": service.__class__.__name__,
                        "error": str(exc),
                    },
                )


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
app.middleware("http")(request_id_middleware)
app.include_router(api_router)
install_custom_openapi(app)


__all__ = ["app"]
