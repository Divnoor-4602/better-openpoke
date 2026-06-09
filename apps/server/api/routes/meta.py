from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ...core.errors import ERROR_RESPONSES
from ...services.timezone_store import get_timezone_store
from ..schemas import TimezoneResponse, TimezoneSetRequest

router = APIRouter(prefix="/meta", tags=["meta"], responses=ERROR_RESPONSES)


@router.post(
    "/timezone",
    response_model=TimezoneResponse,
    operation_id="set_timezone",
    summary="Set user timezone",
)
def set_timezone(payload: TimezoneSetRequest) -> TimezoneResponse:
    store = get_timezone_store()
    try:
        store.set_timezone(payload.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TimezoneResponse(timezone=store.get_timezone())


@router.get(
    "/timezone",
    response_model=TimezoneResponse,
    operation_id="retrieve_timezone",
    summary="Get user timezone",
)
def retrieve_timezone() -> TimezoneResponse:
    store = get_timezone_store()
    return TimezoneResponse(timezone=store.get_timezone())
