"""Google Calendar tool schemas and actions for the execution agent."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from functools import partial
from typing import cast

from server.agents.tool_schemas import TOOL_SCHEMAS
from server.services.execution import get_execution_agent_logs
from server.services.gmail.client import resolve_workspace_gmail_user_id
from server.services.google.client import execute_google_tool
from server.services.memory import record_calendar_tool_result

_CALENDAR_AGENT_NAME = "calendar-execution-agent"

# How far around the requested slot to search for free alternatives when a
# conflict is detected, and how many alternatives to suggest at most.
_CONFLICT_ALT_WINDOW_HOURS = 4
_CONFLICT_ALT_LIMIT = 5


def _parse_iso(value: str) -> datetime:
    """Parse an RFC3339 / ISO 8601 string. Accepts the 'Z' suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _shift_iso(value: str, hours: int) -> str:
    """Return an ISO string shifted by `hours` (positive or negative)."""
    return (_parse_iso(value) + timedelta(hours=hours)).isoformat()


def _extract_busy_windows(
    free_busy_response: object, calendar_id: str
) -> list[tuple[datetime, datetime]]:
    """Pull (start, end) tuples out of a GOOGLESUPER_FREE_BUSY_QUERY response.

    Defensive against the response being wrapped (e.g. `.data` or
    `.response_data` nesting) or the calendar id being missing.
    """
    if not isinstance(free_busy_response, Mapping):
        return []
    # Common nesting variants — pick the first that has `calendars`.
    container: Mapping[str, object] = cast(Mapping[str, object], free_busy_response)
    for key in ("calendars", None):
        if key is None:
            break
        direct = container.get(key)
        if isinstance(direct, Mapping):
            container = {"calendars": cast(Mapping[str, object], direct)}
            break
        nested = container.get("data") or container.get("response_data")
        if isinstance(nested, Mapping):
            nested_map = cast(Mapping[str, object], nested)
            if key in nested_map:
                container = nested_map
                break
    cals_value = container.get("calendars")
    if not isinstance(cals_value, Mapping):
        return []
    cals = cast(Mapping[str, object], cals_value)
    cal = cals.get(calendar_id)
    if not isinstance(cal, Mapping):
        return []
    busy_raw = cast(Mapping[str, object], cal).get("busy")
    if not isinstance(busy_raw, list):
        return []
    out: list[tuple[datetime, datetime]] = []
    for item in cast(list[object], busy_raw):
        if not isinstance(item, Mapping):
            continue
        item_map = cast(Mapping[str, object], item)
        start = item_map.get("start")
        end = item_map.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            out.append((_parse_iso(start), _parse_iso(end)))
        except ValueError:
            continue
    return sorted(out, key=lambda pair: pair[0])


def _compute_free_slots(
    window_start: datetime,
    window_end: datetime,
    busy: list[tuple[datetime, datetime]],
    duration: timedelta,
    limit: int,
) -> list[tuple[datetime, datetime]]:
    """Pick up to `limit` non-overlapping free slots of `duration` length
    between `window_start` and `window_end`, avoiding any `busy` ranges.

    One slot per gap (at the gap start). Simple, predictable; user picks
    from a small spread rather than 20 near-identical options.
    """
    if duration <= timedelta(0) or window_end <= window_start:
        return []
    slots: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for b_start, b_end in busy:
        if b_start > cursor and (b_start - cursor) >= duration:
            slots.append((cursor, cursor + duration))
            if len(slots) >= limit:
                return slots
        if b_end > cursor:
            cursor = b_end
    if (window_end - cursor) >= duration and len(slots) < limit:
        slots.append((cursor, cursor + duration))
    return slots[:limit]


def _check_calendar_conflict(
    composio_user_id: str,
    calendar_id: str,
    start_datetime: str,
    end_datetime: str,
    timezone: str | None,
    memory_id: str | None,
) -> dict[str, object] | None:
    _ = memory_id  # currently unused; kept for parity with caller signature.
    """Run a FREE_BUSY_QUERY over the wider window around the requested
    slot. If the requested slot overlaps a busy window, return a structured
    conflict payload (NOT created). Otherwise return None — caller proceeds
    to CREATE_EVENT.

    Fails open: if the freebusy probe itself errors, return None so the
    create still goes through. The user can always inspect the calendar
    afterward, and Composio errors here would be noisy edge cases.
    """
    try:
        requested_start = _parse_iso(start_datetime)
        requested_end = _parse_iso(end_datetime)
    except ValueError:
        return None
    if requested_end <= requested_start:
        return None

    wide_start_iso = _shift_iso(start_datetime, hours=-_CONFLICT_ALT_WINDOW_HOURS)
    wide_end_iso = _shift_iso(end_datetime, hours=_CONFLICT_ALT_WINDOW_HOURS)

    args: dict[str, object] = {
        "timeMin": wide_start_iso,
        "timeMax": wide_end_iso,
        "items": [{"id": calendar_id}],
    }
    if timezone:
        args["timeZone"] = timezone

    try:
        resp = execute_google_tool(
            "GOOGLESUPER_FREE_BUSY_QUERY",
            composio_user_id,
            arguments=args,
        )
    except Exception:
        return None

    busy = _extract_busy_windows(resp, calendar_id)
    overlaps = [(s, e) for s, e in busy if s < requested_end and e > requested_start]
    if not overlaps:
        return None

    duration = requested_end - requested_start
    free = _compute_free_slots(
        window_start=_parse_iso(wide_start_iso),
        window_end=_parse_iso(wide_end_iso),
        busy=busy,
        duration=duration,
        limit=_CONFLICT_ALT_LIMIT,
    )

    return {
        "conflict": True,
        "calendar_id": calendar_id,
        "requested_start": start_datetime,
        "requested_end": end_datetime,
        "conflicting_busy_windows": [
            {"start": s.isoformat(), "end": e.isoformat()} for s, e in overlaps
        ],
        "suggested_alternatives": [
            {"start": s.isoformat(), "end": e.isoformat()} for s, e in free
        ],
        "instruction": (
            "Do NOT call calendar_create_event again for the same slot. "
            "Report the conflict and the suggested alternatives back to the "
            "interaction agent so the user can pick a different time. Only "
            "retry with force_overlap=true after the user explicitly "
            "confirms scheduling on top of the existing event."
        ),
    }


_SCHEMAS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "List upcoming Google Calendar events for the authenticated user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar identifier, defaults to 'primary'.",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "Lower bound (RFC3339 timestamp, e.g. 2025-01-01T00:00:00Z).",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "Upper bound (RFC3339 timestamp).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Free-text search query across event fields.",
                    },
                    "single_events": {
                        "type": "boolean",
                        "description": "Expand recurring events into instances when true.",
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Sort order: 'startTime' or 'updated'.",
                    },
                    "page_token": {
                        "type": "string",
                        "description": "Pagination token from a previous list call.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_get_event",
            "description": "Retrieve a specific Google Calendar event by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar identifier, defaults to 'primary'.",
                    },
                    "event_id": {
                        "type": "string",
                        "description": "Identifier of the event to fetch.",
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": (
                "Create a Google Calendar event with attendees and optional "
                "Meet link. Runs a freebusy precheck on the primary calendar "
                "first; if the requested slot overlaps an existing event, "
                "returns {conflict: true, suggested_alternatives: [...]} "
                "INSTEAD of creating. Surface the alternatives to the user "
                "and retry with force_overlap=true only after explicit "
                "confirmation to schedule on top of the existing event."
            ),
            # Catalog Zod schema (single source of truth — includes both UI
            # fields and the server-side force_overlap override).
            "parameters": TOOL_SCHEMAS["calendar_create_event"],
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_update_event",
            "description": "Update fields on an existing Google Calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar identifier, defaults to 'primary'.",
                    },
                    "event_id": {
                        "type": "string",
                        "description": "Identifier of the event to update.",
                    },
                    "summary": {"type": "string", "description": "New event title."},
                    "description": {
                        "type": "string",
                        "description": "New event description.",
                    },
                    "location": {"type": "string", "description": "New location."},
                    "start_datetime": {
                        "type": "string",
                        "description": "New start (RFC3339).",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "New end (RFC3339).",
                    },
                    "timezone": {"type": "string", "description": "New IANA timezone."},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Replacement attendee email list.",
                    },
                    "send_updates": {
                        "type": "string",
                        "description": "Notification policy: 'all', 'externalOnly', or 'none'.",
                    },
                    "recurrence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Replacement RRULE/EXRULE/RDATE/EXDATE lines for "
                            "recurring events. Editing this on a series "
                            "rewrites the recurrence pattern for ALL future "
                            "instances. Ask the user before changing."
                        ),
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete_event",
            "description": "Delete a Google Calendar event by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar identifier, defaults to 'primary'.",
                    },
                    "event_id": {
                        "type": "string",
                        "description": "Identifier of the event to delete.",
                    },
                    "send_updates": {
                        "type": "string",
                        "description": "Notification policy: 'all', 'externalOnly', or 'none'.",
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_find_free_slots",
            "description": "Query free/busy info across calendars to find available time windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": "Lower bound of the search window (RFC3339).",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "Upper bound of the search window (RFC3339).",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone for the response.",
                    },
                    "calendar_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Calendar ids (or attendee emails) to inspect.",
                    },
                },
                "required": ["time_min", "time_max"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_calendars",
            "description": "List the calendars the user has access to (primary, secondary, shared). Use to discover calendar IDs before scheduling on a non-primary calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of calendars to return (default 50, max 250).",
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "Include calendars hidden from the user's UI.",
                    },
                    "show_deleted": {
                        "type": "boolean",
                        "description": "Include deleted calendars.",
                    },
                    "min_access_role": {
                        "type": "string",
                        "description": "Filter to calendars where the user has at least this access role: 'freeBusyReader', 'reader', 'writer', or 'owner'.",
                    },
                    "page_token": {
                        "type": "string",
                        "description": "Pagination token from a previous response.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]

# Per-workspace log lookup deferred to call time (no module-level capture).


def get_schemas() -> list[dict[str, object]]:
    """Return Calendar tool schemas."""
    return _SCHEMAS


def _execute(
    tool_name: str,
    composio_user_id: str,
    arguments: dict[str, object],
    memory_id: str | None = None,
) -> dict[str, object]:
    """Execute a Calendar tool and record the action for the execution agent journal."""

    payload = {k: v for k, v in arguments.items() if v is not None}
    payload_str = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else "{}"
    )
    try:
        result = execute_google_tool(tool_name, composio_user_id, arguments=payload)
    except Exception as exc:
        get_execution_agent_logs().record_action(
            _CALENDAR_AGENT_NAME,
            description=f"{tool_name} failed | args={payload_str} | error={exc}",
        )
        raise

    get_execution_agent_logs().record_action(
        _CALENDAR_AGENT_NAME,
        description=f"{tool_name} succeeded | args={payload_str}",
    )
    try:
        _ = record_calendar_tool_result(
            tool_name=tool_name,
            result=result,
            arguments=payload,
            memory_id=memory_id,
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - memory should not break Calendar tools
        get_execution_agent_logs().record_action(
            _CALENDAR_AGENT_NAME,
            description=f"{tool_name} memory recording failed | error={exc}",
        )
    return result


def _require_user() -> str | dict[str, object]:
    composio_user_id = resolve_workspace_gmail_user_id()
    if not composio_user_id:
        return {
            "error": "Google not connected. Please connect Google in settings first."
        }
    return composio_user_id


def calendar_list_events(
    calendar_id: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int | None = None,
    query: str | None = None,
    single_events: bool | None = None,
    order_by: str | None = None,
    page_token: str | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    arguments: dict[str, object] = {
        "calendar_id": calendar_id or "primary",
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": max_results,
        "q": query,
        "singleEvents": single_events,
        "orderBy": order_by,
        "pageToken": page_token,
    }
    return _execute("GOOGLESUPER_EVENTS_LIST", user, arguments, memory_id)


def calendar_get_event(
    event_id: str,
    calendar_id: str | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    arguments: dict[str, object] = {
        "calendar_id": calendar_id or "primary",
        "event_id": event_id,
    }
    return _execute("GOOGLESUPER_EVENTS_GET", user, arguments, memory_id)


def calendar_create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    calendar_id: str | None = None,
    description: str | None = None,
    location: str | None = None,
    timezone: str | None = None,
    attendees: list[str] | None = None,
    create_meeting_room: bool | None = None,
    send_updates: str | None = None,
    recurrence: list[str] | None = None,
    force_overlap: bool | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    effective_calendar_id = calendar_id or "primary"

    # Deterministic conflict precheck on the primary calendar (only one
    # we scope today — see the planning notes). For recurring events, only
    # the FIRST occurrence is checked; future instances may conflict with
    # other recurring series and the user will discover those later.
    # Skipped on force_overlap.
    if not force_overlap:
        conflict = _check_calendar_conflict(
            composio_user_id=user,
            calendar_id=effective_calendar_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            timezone=timezone,
            memory_id=memory_id,
        )
        if conflict is not None:
            if recurrence:
                conflict["note_recurring"] = (
                    "Conflict detected on the FIRST occurrence only. Future "
                    "instances of this recurring event were not checked."
                )
            return conflict

    arguments: dict[str, object] = {
        "calendar_id": effective_calendar_id,
        "summary": summary,
        "description": description,
        "location": location,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "timezone": timezone,
        "attendees": attendees,
        "create_meeting_room": create_meeting_room,
        "send_updates": send_updates,
        "recurrence": recurrence,
    }
    return _execute("GOOGLESUPER_CREATE_EVENT", user, arguments, memory_id)


def calendar_update_event(
    event_id: str,
    calendar_id: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    location: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    timezone: str | None = None,
    attendees: list[str] | None = None,
    send_updates: str | None = None,
    recurrence: list[str] | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    # NOTE: GOOGLESUPER_PATCH_EVENT expects `start_time`/`end_time`
    # (not `start_datetime`/`end_datetime`) — separate from CREATE_EVENT
    # which uses the snake-with-_datetime form. Translating here so the
    # LLM-facing tool schema can stay consistent with create.
    arguments: dict[str, object] = {
        "calendar_id": calendar_id or "primary",
        "event_id": event_id,
        "summary": summary,
        "description": description,
        "location": location,
        "start_time": start_datetime,
        "end_time": end_datetime,
        "timezone": timezone,
        "attendees": attendees,
        "send_updates": send_updates,
        "recurrence": recurrence,
    }
    return _execute("GOOGLESUPER_PATCH_EVENT", user, arguments, memory_id)


def calendar_delete_event(
    event_id: str,
    calendar_id: str | None = None,
    send_updates: str | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    arguments: dict[str, object] = {
        "calendar_id": calendar_id or "primary",
        "event_id": event_id,
        "send_updates": send_updates,
    }
    return _execute("GOOGLESUPER_DELETE_EVENT", user, arguments, memory_id)


def calendar_find_free_slots(
    time_min: str,
    time_max: str,
    timezone: str | None = None,
    calendar_ids: list[str] | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    arguments: dict[str, object] = {
        "time_min": time_min,
        "time_max": time_max,
        "timezone": timezone,
        "items": calendar_ids,
    }
    return _execute("GOOGLESUPER_FIND_FREE_SLOTS", user, arguments, memory_id)


def calendar_list_calendars(
    max_results: int | None = None,
    show_hidden: bool | None = None,
    show_deleted: bool | None = None,
    min_access_role: str | None = None,
    page_token: str | None = None,
    memory_id: str | None = None,
) -> dict[str, object]:
    user = _require_user()
    if isinstance(user, dict):
        return user
    arguments: dict[str, object] = {
        "max_results": max_results,
        "show_hidden": show_hidden,
        "show_deleted": show_deleted,
        "min_access_role": min_access_role,
        "page_token": page_token,
    }
    return _execute("GOOGLESUPER_LIST_CALENDARS", user, arguments, memory_id)


def build_registry(agent_name: str) -> dict[str, Callable[..., object]]:
    """Return Calendar tool callables."""
    return {
        "calendar_list_events": partial(calendar_list_events, memory_id=agent_name),
        "calendar_get_event": partial(calendar_get_event, memory_id=agent_name),
        "calendar_create_event": partial(calendar_create_event, memory_id=agent_name),
        "calendar_update_event": partial(calendar_update_event, memory_id=agent_name),
        "calendar_delete_event": partial(calendar_delete_event, memory_id=agent_name),
        "calendar_find_free_slots": partial(
            calendar_find_free_slots, memory_id=agent_name
        ),
        "calendar_list_calendars": partial(
            calendar_list_calendars, memory_id=agent_name
        ),
    }


__all__ = [
    "build_registry",
    "get_schemas",
    "calendar_list_events",
    "calendar_get_event",
    "calendar_create_event",
    "calendar_update_event",
    "calendar_delete_event",
    "calendar_find_free_slots",
    "calendar_list_calendars",
]
