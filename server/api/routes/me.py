from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.errors import ERROR_RESPONSES
from ..dependencies import get_workspace_id
from ..schemas import MeResponse

router = APIRouter(tags=["auth"], responses=ERROR_RESPONSES)


@router.get(
    "/me",
    response_model=MeResponse,
    operation_id="retrieve_me",
    summary="Return the authenticated caller's workspace",
)
def retrieve_me(workspace_id: Annotated[str, Depends(get_workspace_id)]) -> MeResponse:
    return MeResponse(workspaceId=workspace_id)
