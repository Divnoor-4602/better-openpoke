"""REST endpoints for direct Gmail-draft mutations.

These let the UI act on a draft (send / update / discard) without routing
through the assistant. After every successful action the handler appends a
``<user_action>`` entry to the conversation log so the agent sees the manual
action as context on its next turn — no special prompting needed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from fastapi import APIRouter, HTTPException, status

from ....core.errors import ERROR_RESPONSES
from ....services.conversation import get_conversation_log
from ....services.gmail.drafts import (
    GmailNotConnectedError,
    discard_draft,
    send_draft,
    update_draft,
)
from ...schemas import (
    DraftDiscardResponse,
    DraftSendResponse,
    DraftUpdateRequest,
    DraftUpdateResponse,
)

router = APIRouter(
    prefix="/gmail/drafts",
    tags=["gmail.drafts"],
    responses=ERROR_RESPONSES,
)


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_str(payload: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        result = _str_or_none(value)
        if result is not None:
            return result
    return None


@router.post(
    "/{draft_id}/send",
    response_model=DraftSendResponse,
    operation_id="send_gmail_draft",
    summary="Send a Gmail draft",
)
def send_gmail_draft(draft_id: str) -> DraftSendResponse:
    raw = _invoke(lambda: send_draft(draft_id))
    payload = _composio_payload(raw)
    response_data = payload.get("response_data")
    inner: Mapping[str, object] = (
        cast(Mapping[str, object], response_data)
        if isinstance(response_data, Mapping)
        else payload
    )
    thread_id = _first_str(inner, "threadId", "thread_id")
    message_id = _first_str(inner, "id", "messageId")
    get_conversation_log().record_user_action(
        action="draft_sent",
        summary=f"User sent draft {draft_id} from the UI.",
        payload={
            "draft_id": draft_id,
            "thread_id": thread_id,
            "message_id": message_id,
        },
    )
    return DraftSendResponse(threadId=thread_id, messageId=message_id)


@router.patch(
    "/{draft_id}",
    response_model=DraftUpdateResponse,
    operation_id="update_gmail_draft",
    summary="Update a Gmail draft",
)
def update_gmail_draft(
    draft_id: str, payload: DraftUpdateRequest
) -> DraftUpdateResponse:
    fields = payload.model_dump(exclude_none=True)
    raw = _invoke(lambda: update_draft(draft_id, fields))
    body = _composio_payload(raw)
    response_data = body.get("response_data")
    inner: Mapping[str, object] = (
        cast(Mapping[str, object], response_data)
        if isinstance(response_data, Mapping)
        else body
    )
    new_draft_id = _first_str(inner, "id", "draft_id") or draft_id
    get_conversation_log().record_user_action(
        action="draft_updated",
        summary=f"User edited draft {draft_id} from the UI.",
        payload={"draft_id": new_draft_id, "fields": sorted(fields.keys())},
    )
    return DraftUpdateResponse(draftId=new_draft_id)


@router.delete(
    "/{draft_id}",
    response_model=DraftDiscardResponse,
    operation_id="discard_gmail_draft",
    summary="Discard a Gmail draft",
)
def discard_gmail_draft(draft_id: str) -> DraftDiscardResponse:
    _ = _invoke(lambda: discard_draft(draft_id))
    get_conversation_log().record_user_action(
        action="draft_discarded",
        summary=f"User discarded draft {draft_id} from the UI.",
        payload={"draft_id": draft_id},
    )
    return DraftDiscardResponse()


def _invoke(func: Callable[[], dict[str, object]]) -> dict[str, object]:
    """Run a service call, translating known errors to HTTP responses."""
    try:
        return func()
    except GmailNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc) or "Gmail not connected",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Gmail action failed",
        ) from exc


def _composio_payload(raw: Mapping[str, object]) -> Mapping[str, object]:
    """Composio responses come wrapped — surface the ``data`` block when present.

    Also gate on the ``successful`` flag, raising a 502 with the upstream error
    message rather than silently returning a failed action as success.
    """
    successful = raw.get("successful")
    if successful is False:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(raw.get("error") or "Gmail action failed"),
        )
    data = raw.get("data")
    if isinstance(data, Mapping):
        return cast(Mapping[str, object], data)
    return raw
