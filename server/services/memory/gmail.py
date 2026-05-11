"""Helpers for turning compact Gmail tool payloads into memory events."""

from __future__ import annotations

import re
import uuid
from typing import Any, Iterable, Optional

from .store import MemoryLink, MemoryRecord, MemoryStore, get_memory_store

_NUMBER_PATTERN = re.compile(r"\b\d{6,}\b")


def record_gmail_tool_result(
    *,
    tool_name: str,
    result: dict[str, Any],
    arguments: Optional[dict[str, Any]] = None,
    memory_id: Optional[str] = None,
    store: Optional[MemoryStore] = None,
) -> list[str]:
    """Record memory events from normalized Composio Gmail tool results."""
    memory_store = store or get_memory_store()
    recorded_memory_ids: list[str] = []

    if tool_name == "GMAIL_FETCH_EMAILS":
        for message in _extract_messages(result):
            memory = record_gmail_message(
                message, memory_id=memory_id, store=memory_store
            )
            if memory.memory_id not in recorded_memory_ids:
                recorded_memory_ids.append(memory.memory_id)
        return recorded_memory_ids

    if tool_name == "GMAIL_CREATE_EMAIL_DRAFT":
        memory = _record_gmail_action(
            type="gmail_draft_created",
            tool_name=tool_name,
            result=result,
            arguments=arguments,
            memory_id=memory_id,
            store=memory_store,
        )
        if memory:
            recorded_memory_ids.append(memory.memory_id)
        return recorded_memory_ids

    if tool_name == "GMAIL_REPLY_TO_THREAD":
        memory = _record_gmail_action(
            type="gmail_reply_sent",
            tool_name=tool_name,
            result=result,
            arguments=arguments,
            memory_id=memory_id,
            store=memory_store,
        )
        if memory:
            recorded_memory_ids.append(memory.memory_id)
        return recorded_memory_ids

    if tool_name == "GMAIL_SEND_DRAFT":
        memory = _record_gmail_action(
            type="gmail_draft_sent",
            tool_name=tool_name,
            result=result,
            arguments=arguments,
            memory_id=memory_id,
            store=memory_store,
        )
        if memory:
            recorded_memory_ids.append(memory.memory_id)
        return recorded_memory_ids

    return recorded_memory_ids


def record_gmail_message(
    message: dict[str, Any],
    *,
    memory_id: Optional[str] = None,
    store: Optional[MemoryStore] = None,
) -> MemoryRecord:
    """Record one compact Gmail message event and its thread/message links."""
    memory_store = store or get_memory_store()

    preview = message.get("preview") if isinstance(message.get("preview"), dict) else {}
    message_id = _first_str(message.get("messageId"), message.get("id"))
    thread_id = _first_str(message.get("threadId"), message.get("thread_id"))
    timestamp = _first_str(message.get("messageTimestamp"))
    sender = _first_str(message.get("sender"), _header(message, "From"))
    recipient = _first_str(message.get("to"), _header(message, "To"))
    subject = _first_str(
        message.get("subject"), preview.get("subject"), _header(message, "Subject")
    )
    preview_body = _first_str(preview.get("body"), message.get("body"))
    attachments = _attachment_filenames(message.get("payload"))
    numbers = _numbers(" ".join([subject, preview_body] + attachments))

    links = _compact_links(
        [
            MemoryLink("gmail_thread", thread_id) if thread_id else None,
            MemoryLink("gmail_message", message_id) if message_id else None,
            MemoryLink("email_address", sender) if sender else None,
            MemoryLink("email_address", recipient) if recipient else None,
            *[MemoryLink("attachment", filename) for filename in attachments],
            *[MemoryLink("keyword", number) for number in numbers],
        ]
    )

    title = subject or f"Gmail thread {thread_id or message_id or 'message'}"
    summary = _truncate(
        " ".join(part for part in [sender, subject, preview_body] if part),
        400,
    )

    if memory_id:
        memory = memory_store.get_memory(memory_id)
        if memory is None:
            memory = memory_store.create_memory(
                kind="gmail_thread" if thread_id else "gmail_message",
                title=title,
                summary=summary,
                metadata={"source": "gmail"},
                links=links,
            )
            memory_id = memory.memory_id
        else:
            memory_store.add_links(memory_id, links)
    else:
        memory = memory_store.ensure_memory_for_links(
            kind="gmail_thread" if thread_id else "gmail_message",
            title=title,
            summary=summary,
            metadata={"source": "gmail"},
            links=links,
        )
        memory_id = memory.memory_id

    metadata = {
        "message_id": message_id,
        "thread_id": thread_id,
        "subject": subject,
        "sender": sender,
        "to": recipient,
        "preview": preview_body,
        "attachments": attachments,
    }
    idempotency_key = f"gmail_message:{message_id}" if message_id else None
    memory_store.record_event(
        type="gmail_message_seen",
        text=summary or title,
        memory_id=memory_id,
        idempotency_key=idempotency_key,
        timestamp=timestamp,
        source="gmail",
        metadata=metadata,
        links=links,
    )
    return memory_store.get_memory(memory_id) or memory


def _record_gmail_action(
    *,
    type: str,
    tool_name: str,
    result: dict[str, Any],
    arguments: Optional[dict[str, Any]],
    memory_id: Optional[str],
    store: MemoryStore,
) -> Optional[MemoryRecord]:
    payload = result.get("data") if isinstance(result.get("data"), dict) else result
    args = arguments or {}
    thread_id = _find_key(payload, "threadId", "thread_id", "thread_id")
    if type == "gmail_draft_created":
        message_id = _find_key(payload, "messageId", "message_id")
        draft_id = _first_str(
            _find_key(payload, "draftId", "draft_id", "id"),
            args.get("draft_id"),
        )
    else:
        message_id = _find_key(payload, "messageId", "message_id", "id")
        draft_id = _first_str(
            _find_key(payload, "draftId", "draft_id"), args.get("draft_id")
        )
    subject = _first_str(_find_key(payload, "subject"), args.get("subject"))
    recipient = _first_str(
        _find_key(payload, "recipient_email", "to"),
        args.get("recipient_email"),
        args.get("to"),
    )
    draft_context = _find_draft_context(store, draft_id) if draft_id else {}
    subject = _first_str(subject, draft_context.get("subject"))
    recipient = _first_str(recipient, draft_context.get("recipient_email"), draft_context.get("to"))
    thread_id = _first_str(thread_id, draft_context.get("thread_id"))
    links = _compact_links(
        [
            MemoryLink("gmail_thread", thread_id) if thread_id else None,
            MemoryLink("gmail_message", message_id) if message_id else None,
            MemoryLink("gmail_draft", draft_id) if draft_id else None,
            MemoryLink("email_address", recipient) if recipient else None,
        ]
    )
    if not memory_id and not links:
        return None

    action_label = {
        "gmail_draft_created": "Draft email",
        "gmail_reply_sent": "Reply email",
        "gmail_draft_sent": "Sent email",
    }.get(type, "Email")
    title = _gmail_action_title(action_label, recipient, subject, draft_id)
    summary = _gmail_action_summary(
        action_label=action_label,
        recipient=recipient,
        subject=subject,
        thread_id=thread_id,
        message_id=message_id,
        draft_id=draft_id,
        timestamp=store._now(),
    )
    memory = (
        store.get_memory(memory_id)
        if memory_id
        else store.ensure_memory_for_links(
            kind="gmail_thread" if thread_id else "gmail_action",
            title=title,
            summary=summary,
            metadata={"source": "gmail"},
            links=links,
        )
    )
    if memory is None:
        return None

    store.update_memory(
        memory.memory_id,
        title=title,
        summary=summary,
        metadata={
            "source": "gmail",
            "last_gmail_action": type,
            "last_gmail_recipient": recipient,
            "last_gmail_subject": subject,
            "last_gmail_thread_id": thread_id,
            "last_gmail_message_id": message_id,
            "last_gmail_draft_id": draft_id,
        },
    )

    id_part = draft_id or message_id or result.get("log_id") or uuid.uuid4().hex
    idempotency_key = f"{type}:{id_part}"
    store.record_event(
        type=type,
        text=title,
        memory_id=memory.memory_id,
        idempotency_key=idempotency_key,
        source="gmail",
        metadata={
            "tool_name": tool_name,
            "arguments": _safe_compact(args),
            "result": _safe_compact(result),
        },
        links=links,
    )
    return store.get_memory(memory.memory_id) or memory


def _find_draft_context(store: MemoryStore, draft_id: str) -> dict[str, Any]:
    draft_event = store.find_event_by_link(
        kind="gmail_draft",
        value=draft_id,
        event_type="gmail_draft_created",
    )
    if draft_event is None:
        return {}

    arguments = draft_event.metadata.get("arguments")
    if isinstance(arguments, dict):
        return {
            "recipient_email": _first_str(arguments.get("recipient_email"), arguments.get("to")),
            "subject": _first_str(arguments.get("subject")),
            "thread_id": _first_str(arguments.get("thread_id"), arguments.get("threadId")),
        }

    result = draft_event.metadata.get("result")
    if isinstance(result, dict):
        return {
            "recipient_email": _first_str(result.get("recipient_email"), result.get("to")),
            "subject": _first_str(result.get("subject")),
            "thread_id": _first_str(result.get("thread_id"), result.get("threadId")),
        }
    return {}


def _gmail_action_title(
    action_label: str,
    recipient: str,
    subject: str,
    fallback_id: str,
) -> str:
    target = f" to {recipient}" if recipient else ""
    topic = f": {subject}" if subject else ""
    fallback = f" {fallback_id}" if not target and not topic and fallback_id else ""
    return _truncate(f"{action_label}{target}{topic}{fallback}", 120)


def _gmail_action_summary(
    *,
    action_label: str,
    recipient: str,
    subject: str,
    thread_id: str,
    message_id: str,
    draft_id: str,
    timestamp: str,
) -> str:
    parts = [f"{action_label} recorded at {timestamp}"]
    if recipient:
        parts.append(f"to {recipient}")
    if subject:
        parts.append(f"subject '{subject}'")
    identifiers = []
    if thread_id:
        identifiers.append(f"thread {thread_id}")
    if message_id:
        identifiers.append(f"message {message_id}")
    if draft_id:
        identifiers.append(f"draft {draft_id}")
    if identifiers:
        parts.append("(" + ", ".join(identifiers) + ")")
    return _truncate(" ".join(parts), 400)


def _extract_messages(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    messages = data.get("messages") if isinstance(data, dict) else None
    if isinstance(messages, list):
        return [message for message in messages if isinstance(message, dict)]
    return []


def _attachment_filenames(payload: Any) -> list[str]:
    filenames: list[str] = []

    def walk(part: Any) -> None:
        if not isinstance(part, dict):
            return
        filename = _first_str(part.get("filename"))
        if filename:
            filenames.append(filename)
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    return list(dict.fromkeys(filenames))


def _header(message: dict[str, Any], name: str) -> str:
    payload = message.get("payload")
    headers = payload.get("headers") if isinstance(payload, dict) else []
    for header in headers or []:
        if not isinstance(header, dict):
            continue
        if str(header.get("name") or "").lower() == name.lower():
            return _first_str(header.get("value"))
    return ""


def _numbers(value: str) -> list[str]:
    return list(dict.fromkeys(_NUMBER_PATTERN.findall(value or "")))


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _find_key(payload: Any, *keys: str) -> str:
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


def _compact_links(values: Iterable[Optional[MemoryLink]]) -> list[MemoryLink]:
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


def _safe_compact(result: dict[str, Any]) -> dict[str, Any]:
    raw_data = result.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else result
    compact: dict[str, Any] = {}
    for key in (
        "id",
        "messageId",
        "message_id",
        "threadId",
        "thread_id",
        "draftId",
        "draft_id",
        "subject",
        "recipient_email",
        "to",
        "log_id",
        "successful",
    ):
        if key in data:
            compact[key] = data[key]
        elif key in result:
            compact[key] = result[key]
    return compact


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


__all__ = ["record_gmail_message", "record_gmail_tool_result"]
