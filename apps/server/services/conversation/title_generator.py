from __future__ import annotations

import re

from ...config import get_settings
from ...db.threads import ThreadNotFoundError, ThreadRepository
from ...logging_config import logger
from ...openrouter_client import OpenRouterError, request_chat_completion

MIN_MESSAGES_FOR_TITLE = 3
MAX_MESSAGES_FOR_TITLE = 8
MAX_MESSAGE_CHARS = 900
MAX_TITLE_CHARS = 60

_TITLE_SYSTEM_PROMPT = """Generate a concise title for a conversation.

Rules:
- Use 2-6 words.
- Be specific to the user's actual request.
- No quotes, emojis, or punctuation at the end.
- Return only the title."""


async def generate_thread_title(
    thread_id: str,
    *,
    repository: ThreadRepository,
) -> str | None:
    """Generate and persist a thread title when the thread is still untitled."""

    thread = repository.get_thread(thread_id)
    if thread is None:
        raise ThreadNotFoundError(thread_id)
    if thread.title is not None:
        return thread.title

    messages, _ = repository.list_messages(
        thread_id,
        offset=0,
        limit=MAX_MESSAGES_FOR_TITLE,
    )
    useful_messages = [
        message
        for message in messages
        if message.role in {"user", "assistant"} and message.content.strip()
    ]
    if len(useful_messages) < MIN_MESSAGES_FOR_TITLE:
        return None

    settings = get_settings()
    transcript = "\n".join(
        f"{message.role}: {_compact_content(message.content)}"
        for message in useful_messages
    )

    response = await request_chat_completion(
        model=settings.thread_title_model,
        messages=[
            {
                "role": "user",
                "content": f"Conversation:\n{transcript}\n\nTitle:",
            }
        ],
        system=_TITLE_SYSTEM_PROMPT,
        api_key=settings.openrouter_api_key,
    )
    title = _sanitize_title(_first_choice_content(response))
    if not title:
        logger.warning(
            "thread title generation returned empty title",
            extra={"thread_id": thread_id},
        )
        return None

    _ = repository.update_thread(thread_id, title=title)
    return title


def _compact_content(content: str) -> str:
    text = " ".join(content.split())
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    return f"{text[:MAX_MESSAGE_CHARS].rstrip()}..."


def _first_choice_content(response: object) -> str:
    from collections.abc import Mapping
    from typing import cast as _cast

    if not isinstance(response, Mapping):
        return ""
    response_map = _cast(Mapping[str, object], response)
    choices = response_map.get("choices")
    if not isinstance(choices, list):
        return ""
    choices_list = _cast(list[object], choices)
    if not choices_list:
        return ""
    first = choices_list[0]
    if not isinstance(first, Mapping):
        return ""
    first_map = _cast(Mapping[str, object], first)
    message = first_map.get("message")
    if not isinstance(message, Mapping):
        return ""
    message_map = _cast(Mapping[str, object], message)
    content = message_map.get("content")
    return content if isinstance(content, str) else ""


def _sanitize_title(raw_title: str) -> str:
    title = raw_title.strip().strip('"').strip("'").strip()
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"[.!?;:,]+$", "", title).strip()
    if len(title) <= MAX_TITLE_CHARS:
        return title
    truncated = title[:MAX_TITLE_CHARS].rsplit(" ", 1)[0].strip()
    return truncated or title[:MAX_TITLE_CHARS].strip()


__all__ = ["OpenRouterError", "generate_thread_title"]
