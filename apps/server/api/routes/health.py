from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...config import Settings, get_settings
from ...core.errors import ERROR_RESPONSES
from ..schemas import HealthResponse

router = APIRouter(tags=["health"], responses=ERROR_RESPONSES)


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="retrieve_health",
    summary="Get API health",
)
def retrieve_health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(ok=True, service="general-poke", version=settings.app_version)
