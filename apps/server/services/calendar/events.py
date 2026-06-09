"""Direct Google Calendar event mutations for the REST layer.

Mirrors ``server/services/gmail/drafts.py``. Wraps Composio's
``GOOGLESUPER_PATCH_EVENT`` and ``GOOGLESUPER_DELETE_EVENT`` for use by
``server/api/routes/calendar/events.py``. Kept separate from the
LLM-tool wrappers in ``apps/server/agents/execution_agent/tools/calendar.py``
(which return agent-shaped payloads and write to memory/journals); REST
handlers just need the raw normalized Composio response plus a clear
"not connected" signal.

UI-driven changes always pass ``send_updates='all'`` so attendees see the
edit / cancellation immediately — matches the product decision that
manual actions are loud, not silent.
"""

from __future__ import annotations


from ..gmail.client import (
    JsonDict,
    execute_google_tool,
    resolve_workspace_gmail_user_id,
)

_DEFAULT_CALENDAR_ID = "primary"
_DEFAULT_SEND_UPDATES = "all"


class CalendarNotConnectedError(RuntimeError):
    """Raised when no active Google connection exists for the current user."""


def _require_user() -> str:
    user_id = resolve_workspace_gmail_user_id()
    if not user_id:
        raise CalendarNotConnectedError("No active Google connection")
    return user_id


def update_event(
    event_id: str,
    fields: dict[str, object],
    calendar_id: str | None = None,
) -> JsonDict:
    """Patch an event via ``GOOGLESUPER_PATCH_EVENT``.

    ``fields`` is a flat partial — ``summary``, ``description``,
    ``attendees`` are all optional. Only non-``None`` values are forwarded
    so a partial PATCH doesn't clobber unset fields server-side.

    Note: PATCH_EVENT uses the same flat field names for these editable
    keys (``summary``, ``description``, ``attendees``); the field-name
    translation (``start_datetime`` → ``start_time``) only matters for
    datetime mutations, which are explicitly out of scope for the UI
    PATCH path (agent-only).
    """
    arguments: dict[str, object] = {
        "calendar_id": calendar_id or _DEFAULT_CALENDAR_ID,
        "event_id": event_id,
        "send_updates": _DEFAULT_SEND_UPDATES,
    }
    for key, value in fields.items():
        if value is not None:
            arguments[key] = value
    return execute_google_tool(
        "GOOGLESUPER_PATCH_EVENT",
        _require_user(),
        arguments=arguments,
    )


def discard_event(
    event_id: str,
    calendar_id: str | None = None,
) -> JsonDict:
    """Delete an event via ``GOOGLESUPER_DELETE_EVENT``.

    For recurring events this removes the ENTIRE series — Google Calendar
    treats DELETE on the parent event id as cancelling all occurrences.
    Per-instance deletion is not supported on this path; surface that as a
    limitation if the user asks.
    """
    return execute_google_tool(
        "GOOGLESUPER_DELETE_EVENT",
        _require_user(),
        arguments={
            "event_id": event_id,
            "calendar_id": calendar_id or _DEFAULT_CALENDAR_ID,
            "send_updates": _DEFAULT_SEND_UPDATES,
        },
    )
