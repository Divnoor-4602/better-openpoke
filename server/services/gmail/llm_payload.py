"""Shrink Gmail tool responses before they go back to the LLM.

Composio's Gmail tools return full MIME-encoded payloads (headers, base64
bodies, attachment lists). Feeding that back to the model wastes 30-50K
tokens per response and adds 5-10s of TTFT per post-tool LLM pass. This
module trims responses to the minimum the LLM needs to answer
"what's in my inbox" style questions: subject, sender, recipient,
internalDate, short snippet, label ids, attachment flag.

Scope is intentionally narrow: only the discovery/browse tool
``gmail_fetch_emails`` (Composio slug ``GOOGLESUPER_FETCH_EMAILS``) is
shrunk. Single-message reads (``gmail_fetch_message_by_id``) and
thread reads (``gmail_fetch_thread``) keep their full payloads so the
agent can still draft replies and answer detail questions.

If the agent needs a full body, it should follow up with
``gmail_fetch_message_by_id`` (``format='full'``) for that specific
message.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .processing import EmailTextCleaner, build_processed_email

_GMAIL_BROWSE_TOOLS: frozenset[str] = frozenset(
    {
        # Composio slug
        "GOOGLESUPER_FETCH_EMAILS",
        # Agent-facing schema name
        "gmail_fetch_emails",
    }
)


def shrink_gmail_tool_result(
    tool_name: str,
    payload: object,
    *,
    snippet_max_chars: int = 150,
) -> object:
    """Return a smaller payload for Gmail browse tools, or the input unchanged.

    Fail-open: if the payload shape is unrecognized or shrinking raises,
    return the original payload so the LLM still sees the data.
    """

    if tool_name not in _GMAIL_BROWSE_TOOLS:
        return payload

    try:
        raw_messages, next_page_token = _locate_messages(payload)
    except Exception:
        return payload

    if not raw_messages:
        return payload

    cleaner = EmailTextCleaner()
    shrunk_messages: list[dict[str, object]] = []
    for raw_message in raw_messages:
        if not isinstance(raw_message, Mapping):
            continue
        message_map = cast(Mapping[str, object], raw_message)
        try:
            processed = build_processed_email(
                dict(message_map), query="", cleaner=cleaner
            )
        except Exception:
            processed = None
        if processed is None:
            continue

        snippet_source = processed.clean_text or _fallback_snippet(message_map)
        snippet = _truncate_snippet(snippet_source, snippet_max_chars)

        shrunk_messages.append(
            {
                "messageId": processed.id,
                "threadId": processed.thread_id,
                "subject": processed.subject,
                "from": processed.sender,
                "to": processed.recipient,
                "internalDate": (
                    processed.timestamp.isoformat() if processed.timestamp else None
                ),
                "snippet": snippet,
                "labelIds": processed.label_ids,
                "hasAttachment": processed.has_attachments,
                "attachmentCount": processed.attachment_count,
            }
        )

    if not shrunk_messages:
        return payload

    return {
        "messages": shrunk_messages,
        "nextPageToken": next_page_token,
        "shrunken": True,
    }


def _locate_messages(payload: object) -> tuple[list[object], str | None]:
    """Find the messages list + nextPageToken across Composio response shapes."""

    next_page: str | None = None
    if not isinstance(payload, Mapping):
        return [], next_page
    payload_map = cast(Mapping[str, object], payload)

    data_section: Mapping[str, object] | None = None
    data_candidate = payload_map.get("data")
    if isinstance(data_candidate, Mapping):
        data_section = cast(Mapping[str, object], data_candidate)
        token = data_section.get("nextPageToken")
        if isinstance(token, str):
            next_page = token

    messages: list[object] = []
    for container in (data_section, payload_map):
        if container is None:
            continue
        candidate = container.get("messages")
        if isinstance(candidate, list):
            messages = cast(list[object], candidate)
            break

    if next_page is None:
        token = payload_map.get("nextPageToken")
        if isinstance(token, str):
            next_page = token

    return messages, next_page


def _fallback_snippet(message: Mapping[str, object]) -> str:
    """Pull a snippet from preview.body / preview.subject / message.body when
    the cleaner could not decode the payload (e.g. Composio returned only
    a ``preview`` block without raw MIME bodies)."""

    preview_candidate = message.get("preview")
    if isinstance(preview_candidate, Mapping):
        preview = cast(Mapping[str, object], preview_candidate)
        for key in ("body", "subject"):
            value = preview.get(key)
            if isinstance(value, str) and value.strip():
                return value
    body = message.get("body")
    if isinstance(body, str) and body.strip():
        return body
    return ""


def _truncate_snippet(text: str, limit: int) -> str:
    if not text:
        return ""
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: max(0, limit - 1)].rstrip() + "…"


__all__ = ["shrink_gmail_tool_result"]
