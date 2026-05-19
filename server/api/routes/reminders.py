from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...core.errors import ERROR_RESPONSES
from ...services.reminders import get_reminder_event_bus
from ..dependencies import get_workspace_id

router = APIRouter(tags=["reminders"], responses=ERROR_RESPONSES)


@router.get(
    "/reminders/events",
    response_model=None,
    responses={
        200: {
            "description": "SSE stream of reminder.fired events for this workspace.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **ERROR_RESPONSES,
    },
    operation_id="stream_reminder_events",
    summary="Stream reminder fire events",
)
async def stream_reminder_events(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        bus = get_reminder_event_bus()
        queue = bus.subscribe(workspace_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {event.model_dump_json()}\n\n"
        finally:
            bus.unsubscribe(workspace_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache"},
    )
