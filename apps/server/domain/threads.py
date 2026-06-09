from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadEntity:
    thread_id: str
    title: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MessageEntity:
    message_id: str
    thread_id: str
    role: str
    content: str
    parts_json: str | None
    created_at: str
    turn_index: int = 0
