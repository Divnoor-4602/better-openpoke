"""Interaction agent helpers for prompt construction."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import cast

from ...config import get_settings
from ...logging_config import logger
from ...services.execution import get_execution_event_store
from ...services.memory import MemoryEvent, MemorySearchResult, get_memory_store

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt(notifications: str | None = None) -> str:
    """Return the system prompt for the interaction agent.

    ``notifications`` is the browser's ``Notification.permission`` value
    ("granted" | "default" | "denied") as snapshotted at request time. It
    governs how the agent confirms a freshly-scheduled reminder.
    """
    state = (notifications or "default").lower()
    if state not in {"granted", "default", "denied"}:
        state = "default"
    return f"{SYSTEM_PROMPT}\n\n<notification_permission>{state}</notification_permission>"


# Build structured message with conversation history, relevant memories, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    recent_transcript: str = "",
    message_type: str = "user",
) -> list[dict[str, str]]:
    """Compose a message that bundles history, relevant memories, and the latest turn."""
    sections: list[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(_render_recent_conversation_entries(recent_transcript))
    sections.append(_render_active_execution_runs())
    relevant_memories = _render_relevant_memories(latest_text)
    sections.append(f"<relevant_memories>\n{relevant_memories}\n</relevant_memories>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    if 'reason="' in relevant_memories and "bge rerank" in relevant_memories:
        include_content = get_settings().memory_debug_log_content
        extra: dict[str, object] = {
            "message_type": message_type,
            "latest_text_chars": len(latest_text),
            "prompt_content_chars": len(content),
        }
        if include_content:
            extra.update({"latest_text": latest_text, "prompt_content": content})
        logger.debug(
            "Interaction prompt with reranked memories",
            extra=extra,
        )
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


def _render_recent_conversation_entries(transcript: str) -> str:
    recent = transcript.strip()
    if not recent:
        recent = "None"
    return f"<recent_conversation_entries>\n{recent}\n</recent_conversation_entries>"


def _render_active_execution_runs() -> str:
    runs = [
        run
        for run in get_execution_event_store().list_runs(limit=50)
        if run.get("status") in {"queued", "running"}
    ]
    if not runs:
        return "<active_execution_runs>\nNone\n</active_execution_runs>"

    rendered: list[str] = []
    for run in runs[:12]:
        parts = run.get("parts") or []
        latest_text = ""
        if parts:
            event_map = cast(dict[str, object], cast(object, parts[-1]))
            latest_text = str(
                event_map.get("text")
                or event_map.get("toolName")
                or event_map.get("state")
                or ""
            )
        rendered.append(
            "\n".join(
                [
                    (
                        f'<run request_id="{escape(str(run.get("requestId") or ""), quote=True)}" '
                        f'memory_id="{escape(str(run.get("memoryId") or ""), quote=True)}" '
                        f'status="{escape(str(run.get("status") or ""), quote=True)}">'
                    ),
                    f"<title>{escape(str(run.get('title') or ''), quote=False)}</title>",
                    f"<latest>{escape(_truncate(latest_text, 240), quote=False)}</latest>",
                    "</run>",
                ]
            )
        )
    return (
        f"<active_execution_runs>\n{chr(10).join(rendered)}\n</active_execution_runs>"
    )


# Format relevant memories into XML tags for LLM awareness
def _render_relevant_memories(query: str) -> str:
    memories = get_memory_store().search(query, limit=8, context="prompt_context")

    if not memories:
        return "None"

    rendered: list[str] = []
    for rank, result in enumerate(memories, start=1):
        rendered.append(_render_memory_result(result, rank))
    rendered_content = "\n".join(rendered)
    _log_prompt_memories(
        query=query, memories=memories, rendered_content=rendered_content
    )

    logger.debug(
        "Prompt memory search results",
        extra={
            "query_length": len(query),
            "count": len(memories),
            "reranked": any("bge rerank" in result.reason for result in memories),
            "matches": [
                {
                    "rank": rank,
                    "memory_id": result.memory.memory_id,
                    "title": result.memory.title,
                    "score": round(result.score, 3),
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "events": [
                        _log_event(event) for event in result.memory.recent_events[-3:]
                    ],
                }
                for rank, result in enumerate(memories, start=1)
            ],
        },
    )
    return rendered_content


def _log_prompt_memories(
    *,
    query: str,
    memories: list[MemorySearchResult],
    rendered_content: str,
) -> None:
    include_content = get_settings().memory_debug_log_content
    lines = [
        "Interaction prompt relevant memories",
        (
            f'query_chars="{len(query)}" memories="{len(memories)}" '
            f'rendered_chars="{len(rendered_content)}" debug_content="{include_content}"'
        ),
        "<prompt_memories>",
    ]
    for rank, result in enumerate(memories, start=1):
        memory = result.memory
        lines.append(
            " ".join(
                [
                    f'rank="{rank}"',
                    f'memory_id="{memory.memory_id}"',
                    f'kind="{memory.kind}"',
                    f'score="{result.score:.4f}"',
                    f'confidence="{result.confidence}"',
                    f'reason="{result.reason}"',
                    f'title="{_truncate(memory.title, 120)}"',
                ]
            )
        )
        links = [
            f"{link.kind}:{_truncate(link.value, 80)}" for link in memory.links[:8]
        ]
        if links:
            lines.append(f"links={links!r}")
        lines.append("<recent_events>")
        for event in memory.recent_events[-5:]:
            line = (
                f'event_id="{event.event_id}" type="{event.type}" '
                f'timestamp="{event.timestamp or event.recorded_at}"'
            )
            if include_content:
                line += f" text={_truncate(event.text, 240)!r}"
            lines.append(line)
        lines.append("</recent_events>")
    if include_content:
        lines.extend(
            [
                "<rendered_relevant_memories>",
                rendered_content,
                "</rendered_relevant_memories>",
            ]
        )
    lines.append("</prompt_memories>")
    logger.debug("\n".join(lines))


def _render_memory_result(result: MemorySearchResult, rank: int) -> str:
    memory = result.memory
    memory_id = escape(memory.memory_id, quote=True)
    kind = escape(memory.kind, quote=True)
    title = escape(memory.title, quote=False)
    summary = escape(memory.summary or "None", quote=False)
    reason = escape(result.reason, quote=True)
    confidence = escape(result.confidence, quote=True)
    links = "\n".join(
        _render_memory_link(link.kind, link.value) for link in memory.links[:8]
    )
    if not links:
        links = "None"
    events = "\n".join(
        (
            f'<event type="{escape(event.type, quote=True)}" '
            f'timestamp="{escape(event.timestamp or event.recorded_at, quote=True)}">'
            f"{escape(event.text, quote=False)}</event>"
        )
        for event in memory.recent_events[-5:]
    )
    if not events:
        events = "None"
    return "\n".join(
        [
            (
                f'<memory id="{memory_id}" kind="{kind}" rank="{rank}" '
                f'score="{result.score:.2f}" confidence="{confidence}" reason="{reason}">'
            ),
            f"<title>{title}</title>",
            f"<summary>{summary}</summary>",
            f"<links>\n{links}\n</links>",
            f"<recent_events>\n{events}\n</recent_events>",
            "</memory>",
        ]
    )


def _render_memory_link(kind: str, value: str) -> str:
    safe_value = escape(value, quote=True)
    if kind == "gmail_thread":
        return f'<gmail_thread id="{safe_value}" />'
    if kind == "gmail_message":
        return f'<gmail_message id="{safe_value}" />'
    if kind == "email_address":
        return f'<email value="{safe_value}" />'
    safe_kind = escape(kind, quote=True)
    return f'<link kind="{safe_kind}" value="{safe_value}" />'


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"


def _truncate(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _log_event(event: MemoryEvent) -> dict[str, str]:
    payload = {"event_id": event.event_id, "type": event.type}
    if get_settings().memory_debug_log_content:
        payload["text"] = _truncate(event.text, 180)
    return payload
