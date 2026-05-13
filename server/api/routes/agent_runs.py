from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ...core.errors import ERROR_RESPONSES
from ...core.pagination import CursorPage, decode_cursor, encode_cursor
from ...routes.execution import execution_run_stream
from ...services.execution import get_execution_event_store
from ..converters import agent_run_resource
from ..schemas import AgentRunListResponse, AgentRunResponse

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"], responses=ERROR_RESPONSES)


@router.get(
    "",
    response_model=AgentRunListResponse,
    operation_id="list_agent_runs",
    summary="List agent runs",
)
def list_agent_runs(
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> AgentRunListResponse:
    offset = decode_cursor(cursor)
    runs = get_execution_event_store().list_runs(limit=limit, offset=offset)
    next_offset = offset + limit if len(runs) == limit else None
    return AgentRunListResponse(
        items=[agent_run_resource(run) for run in runs],
        page=CursorPage(nextCursor=encode_cursor(next_offset), limit=limit),
    )


@router.get(
    "/{requestId}",
    response_model=AgentRunResponse,
    operation_id="retrieve_agent_run",
    summary="Get an agent run",
)
def retrieve_agent_run(requestId: str) -> AgentRunResponse:
    run = get_execution_event_store().get_run(requestId)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return AgentRunResponse(run=agent_run_resource(run))


@router.get(
    "/{requestId}/stream",
    response_model=None,
    responses={
        200: {
            "description": "AI SDK UI message stream for agent run events",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **ERROR_RESPONSES,
    },
    operation_id="stream_agent_run_events",
    summary="Stream agent run events",
)
def stream_agent_run_events(
    requestId: str,
    afterId: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    return execution_run_stream(requestId, after_id=afterId)
