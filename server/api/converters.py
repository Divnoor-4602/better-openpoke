from __future__ import annotations

import json
from typing import Any, cast

from ..domain.threads import MessageEntity, ThreadEntity
from ..services.execution import ExecutionRun
from .schemas import AgentRunResource, MessageResource, ThreadResource


def thread_resource(thread: ThreadEntity) -> ThreadResource:
    return ThreadResource(
        threadId=thread.thread_id,
        title=thread.title,
        createdAt=thread.created_at,
        updatedAt=thread.updated_at,
    )


def message_resource(message: MessageEntity) -> MessageResource:
    parts: list[dict[str, Any]] = []
    if message.parts_json:
        try:
            loaded = json.loads(message.parts_json)
            if isinstance(loaded, list):
                parts = [item for item in loaded if isinstance(item, dict)]
        except json.JSONDecodeError:
            parts = []
    return MessageResource(
        messageId=message.message_id,
        threadId=message.thread_id,
        role=cast(Any, message.role),
        content=message.content,
        parts=cast(Any, parts),
        createdAt=message.created_at,
    )


def agent_run_resource(run: ExecutionRun) -> AgentRunResource:
    return AgentRunResource(
        requestId=run["requestId"],
        memoryId=run["memoryId"],
        threadId=run.get("threadId"),
        parentMemoryId=run["parentMemoryId"],
        title=run["title"],
        status=run["status"],
        ok=run["ok"],
        createdAt=run["createdAt"],
        updatedAt=run["updatedAt"],
        parts=cast(Any, run["parts"]),
    )

