"""REST endpoints for direct Google Calendar event mutations.

Lets the UI patch/discard an event without routing through the assistant.
After every successful action the handler appends a ``<user_action>`` entry
to the conversation log so the agent sees the manual action as context on
its next turn — same pattern as ``routes/gmail/drafts.py``.

No ``send`` endpoint: calendar events have no draft → send lifecycle, the
create is the publish.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from fastapi import APIRouter, HTTPException, status

from ....core.errors import ERROR_RESPONSES
from ....services.calendar.events import (
    CalendarNotConnectedError,
    discard_event,
    update_event,
)
from ....services.conversation import get_conversation_log
from ...schemas import (
    CalendarEventDiscardResponse,
    CalendarEventUpdateRequest,
    CalendarEventUpdateResponse,
)

router = APIRouter(
    prefix="/calendar/events",
    tags=["calendar.events"],
    responses=ERROR_RESPONSES,
)


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_str(payload: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        result = _str_or_none(payload.get(key))
        if result is not None:
            return result
    return None


@router.patch(
    "/{event_id}",
    response_model=CalendarEventUpdateResponse,
    operation_id="update_calendar_event",
    summary="Update a Google Calendar event",
)
def update_calendar_event(
    event_id: str, payload: CalendarEventUpdateRequest
) -> CalendarEventUpdateResponse:
    fields = payload.model_dump(exclude_none=True)
    raw = _invoke(lambda: update_event(event_id, fields))
    body = _composio_payload(raw)
    response_data = body.get("response_data")
    inner: Mapping[str, object] = (
        cast(Mapping[str, object], response_data)
        if isinstance(response_data, Mapping)
        else body
    )
    new_event_id = _first_str(inner, "id", "event_id") or event_id
    get_conversation_log().record_user_action(
        action="event_updated",
        summary=f"User edited event {event_id} from the UI.",
        payload={"event_id": new_event_id, "fields": sorted(fields.keys())},
    )
    return CalendarEventUpdateResponse(eventId=new_event_id)


@router.delete(
    "/{event_id}",
    response_model=CalendarEventDiscardResponse,
    operation_id="discard_calendar_event",
    summary="Discard a Google Calendar event",
)
def discard_calendar_event(event_id: str) -> CalendarEventDiscardResponse:
    _ = _invoke(lambda: discard_event(event_id))
    get_conversation_log().record_user_action(
        action="event_discarded",
        summary=f"User discarded event {event_id} from the UI.",
        payload={"event_id": event_id},
    )
    return CalendarEventDiscardResponse()


def _invoke(func: Callable[[], dict[str, object]]) -> dict[str, object]:
    """Run a service call, translating known errors to HTTP responses."""
    try:
        return func()
    except CalendarNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc) or "Google Calendar not connected",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Calendar action failed",
        ) from exc


def _composio_payload(raw: Mapping[str, object]) -> Mapping[str, object]:
    """Composio responses come wrapped — surface the ``data`` block when present.

    Also gate on the ``successful`` flag, raising a 502 with the upstream
    error message rather than silently returning a failed action as success.
    """
    successful = raw.get("successful")
    if successful is False:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(raw.get("error") or "Calendar action failed"),
        )
    data = raw.get("data")
    if isinstance(data, Mapping):
        return cast(Mapping[str, object], data)
    return raw
