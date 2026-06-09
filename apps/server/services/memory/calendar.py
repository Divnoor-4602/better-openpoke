"""Record Google Calendar tool results as memory events."""
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import cast

from .store import MemoryLink, MemoryRecord, MemoryStore, get_memory_store


def record_calendar_tool_result(
    *,
    tool_name: str,
    result: dict[str, object],
    arguments: dict[str, object] | None = None,
    memory_id: str | None = None,
    store: MemoryStore | None = None,
) -> list[str]:
    """Record memory events from Composio Google Calendar tool results."""
    memory_store = store or get_memory_store()
    recorded: list[str] = []

    payload = _dict_value(result.get("data")) or result
    args = arguments or {}

    event_type_map = {
        "GOOGLESUPER_CREATE_EVENT": "calendar_event_created",
        "GOOGLESUPER_PATCH_EVENT": "calendar_event_updated",
        "GOOGLESUPER_DELETE_EVENT": "calendar_event_deleted",
        "GOOGLESUPER_EVENTS_GET": "calendar_event_fetched",
        "GOOGLESUPER_EVENTS_LIST": "calendar_events_listed",
        "GOOGLESUPER_FIND_FREE_SLOTS": "calendar_free_slots_queried",
        "GOOGLESUPER_LIST_CALENDARS": "calendar_calendars_listed",
    }
    event_type = event_type_map.get(tool_name)
    if not event_type:
        return recorded

    event_id = _first_str(
        _find_key(payload, "id", "eventId", "event_id"),
        args.get("event_id"),
    )
    summary = _first_str(_find_key(payload, "summary"), args.get("summary"))
    start = _first_str(_find_key(payload, "start_time", "startTime"))
    attendees = _attendee_emails(payload) or _attendee_emails(args)

    links = _compact_links(
        [
            MemoryLink("calendar_event", event_id) if event_id else None,
            *[MemoryLink("email_address", email) for email in attendees],
        ]
    )

    title = _title(event_type, summary, event_id)
    summary_text = _summary_text(event_type, summary, start, attendees, event_id)

    memory = _resolve_memory(
        store=memory_store,
        inherited_memory_id=memory_id,
        title=title,
        summary=summary_text,
        links=links,
    )
    if memory is None:
        return recorded

    _ = memory_store.update_memory(
        memory.memory_id,
        title=title,
        summary=summary_text,
        metadata={
            "source": "google_calendar",
            "last_calendar_action": event_type,
            "last_calendar_event_id": event_id,
            "last_calendar_summary": summary,
        },
    )

    id_part = event_id or result.get("log_id") or uuid.uuid4().hex
    _ = memory_store.record_event(
        type=event_type,
        text=title,
        memory_id=memory.memory_id,
        idempotency_key=f"{event_type}:{id_part}",
        source="google_calendar",
        metadata={
            "tool_name": tool_name,
            "arguments": _safe_compact(args),
            "result": _safe_compact(result),
        },
        links=links,
    )
    recorded.append(memory.memory_id)
    return recorded


def _resolve_memory(
    *,
    store: MemoryStore,
    inherited_memory_id: str | None,
    title: str,
    summary: str,
    links: list[MemoryLink],
) -> MemoryRecord | None:
    if links:
        return store.ensure_memory_for_links(
            kind="calendar_event",
            title=title,
            summary=summary,
            metadata={"source": "google_calendar"},
            links=links,
        )
    if inherited_memory_id:
        return store.get_memory(inherited_memory_id)
    return None


def _title(event_type: str, summary: str, event_id: str) -> str:
    label = {
        "calendar_event_created": "Calendar event",
        "calendar_event_updated": "Calendar event updated",
        "calendar_event_deleted": "Calendar event deleted",
        "calendar_event_fetched": "Calendar event",
        "calendar_events_listed": "Calendar events",
        "calendar_free_slots_queried": "Calendar free slots",
    }.get(event_type, "Calendar event")
    if summary:
        return _truncate(f"{label}: {summary}", 120)
    if event_id:
        return _truncate(f"{label} {event_id}", 120)
    return label


def _summary_text(
    event_type: str,
    summary: str,
    start: str,
    attendees: list[str],
    event_id: str,
) -> str:
    parts: list[str] = [event_type.replace("_", " ")]
    if summary:
        parts.append(f"'{summary}'")
    if start:
        parts.append(f"at {start}")
    if attendees:
        parts.append(f"with {', '.join(attendees[:5])}")
    if event_id:
        parts.append(f"(event {event_id})")
    return _truncate(" ".join(parts), 400)


def _attendee_emails(payload: object) -> list[str]:
    emails: list[str] = []
    if isinstance(payload, dict):
        attendees = payload.get("attendees")
        if isinstance(attendees, list):
            for entry in attendees:
                if isinstance(entry, dict):
                    email = _first_str(entry.get("email"))
                elif isinstance(entry, str):
                    email = entry.strip()
                else:
                    email = ""
                if email and email not in emails:
                    emails.append(email)
    return emails


def _compact_links(values: Iterable[MemoryLink | None]) -> list[MemoryLink]:
    links: list[MemoryLink] = []
    seen: set[tuple[str, str]] = set()
    for link in values:
        if link is None or not link.value:
            continue
        key = (link.kind, link.value)
        if key not in seen:
            links.append(link)
            seen.add(key)
    return links


def _safe_compact(payload: dict[str, object]) -> dict[str, object]:
    keys = (
        "id",
        "eventId",
        "event_id",
        "summary",
        "start_time",
        "startTime",
        "end_time",
        "endTime",
        "meet_link",
        "hangoutLink",
        "successful",
    )
    return {k: payload[k] for k in keys if k in payload}


def _first_str(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _dict_value(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _find_key(payload: object, *keys: str) -> str:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _find_key(value, *keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_key(item, *keys)
            if found:
                return found
    return ""


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


__all__ = ["record_calendar_tool_result"]
