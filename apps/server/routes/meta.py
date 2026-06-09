from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.routing import BaseRoute

from ..config import Settings, get_settings
from ..models import (
    HealthResponse,
    RootResponse,
    SetTimezoneRequest,
    SetTimezoneResponse,
)
from ..services import get_timezone_store
from ..services.memory.indexer import MemoryIndexer
from ..services.memory.store import _MEMORY_DB_PATH  # pyright: ignore[reportPrivateUsage]

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
# Return service health status for monitoring and load balancers
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(ok=True, service="general-poke", version=settings.app_version)


@router.get("/meta", response_model=RootResponse)
# Return service metadata including available API endpoints
def meta(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RootResponse:
    app = cast(object, request.app)
    app_routes = cast(list[BaseRoute], cast(object, getattr(app, "routes")))
    endpoints = sorted(
        {
            path
            for route in app_routes
            for path in [_route_path(route)]
            if path is not None
            and getattr(route, "include_in_schema", False)
            and path.startswith("/api/")
        }
    )
    return RootResponse(
        status="ok",
        service="general-poke",
        version=settings.app_version,
        endpoints=endpoints,
    )


def _route_path(route: BaseRoute) -> str | None:
    path = cast(object, getattr(route, "path", None))
    return path if isinstance(path, str) else None


@router.post("/meta/timezone", response_model=SetTimezoneResponse)
# Set the user's timezone for proper email timestamp formatting
def set_timezone(payload: SetTimezoneRequest) -> SetTimezoneResponse:
    store = get_timezone_store()
    try:
        store.set_timezone(payload.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SetTimezoneResponse(timezone=store.get_timezone())


@router.get("/meta/timezone", response_model=SetTimezoneResponse)
def get_timezone() -> SetTimezoneResponse:
    store = get_timezone_store()
    return SetTimezoneResponse(timezone=store.get_timezone())


@router.get("/meta/memory-index")
def memory_index_status() -> dict[str, object]:
    """Return concise memory indexing queue health."""
    return MemoryIndexer(_MEMORY_DB_PATH).queue_stats()
