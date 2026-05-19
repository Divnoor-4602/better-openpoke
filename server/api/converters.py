from __future__ import annotations

import json
from typing import cast

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
    parts: list[dict[str, object]] = []
    if message.parts_json:
        try:
            loaded = cast(object, json.loads(message.parts_json))
            if isinstance(loaded, list):
                loaded_list = cast(list[object], loaded)
                parts = [
                    cast(dict[str, object], item)
                    for item in loaded_list
                    if isinstance(item, dict)
                ]
        except json.JSONDecodeError:
            parts = []
    # Use model_validate so pydantic coerces the raw `parts` dicts into the
    # `TextUIPart | GenericUIPart` union without us having to manually
    # discriminate here.
    return MessageResource.model_validate(
        {
            "messageId": message.message_id,
            "threadId": message.thread_id,
            "role": message.role,
            "content": message.content,
            "parts": parts,
            "createdAt": message.created_at,
            "turnIndex": message.turn_index,
        }
    )


def agent_run_resource(run: ExecutionRun) -> AgentRunResource:
    return AgentRunResource.model_validate(
        {
            "runId": run["runId"],
            "requestId": run["requestId"],
            "memoryId": run["memoryId"],
            "threadId": run.get("threadId"),
            "parentMemoryId": run["parentMemoryId"],
            "parentRunId": run["parentRunId"],
            "scope": run["scope"],
            "title": run["title"],
            "status": run["status"],
            "ok": run["ok"],
            "createdAt": run["createdAt"],
            "updatedAt": run["updatedAt"],
            "parts": run["parts"],
        }
    )
