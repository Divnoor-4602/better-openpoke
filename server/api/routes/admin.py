from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.errors import ERROR_RESPONSES
from ...db.workspace_registry import get_workspace_registry

router = APIRouter(prefix="/admin", tags=["admin"], responses=ERROR_RESPONSES)


class WorkspaceListEntry(BaseModel):
    workspaceId: str
    firstSeenAt: str
    firstIp: str | None = None


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceListEntry]


@router.get(
    "/workspaces",
    response_model=WorkspaceListResponse,
    operation_id="list_workspaces",
    summary="List all workspaces registered on this server (demo visibility)",
)
def list_workspaces() -> WorkspaceListResponse:
    rows = get_workspace_registry().list_all()
    items = [WorkspaceListEntry.model_validate(row) for row in rows]
    return WorkspaceListResponse(items=items)
