from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..agents.interaction_agent.runtime import InteractionAgentRuntime
from ..core.workspace_context import require_current_workspace
from ..services.conversation import ui_stream
from ..services.execution import (
    ExecutionEvent,
    ExecutionEventPayload,
    ExecutionRun,
    get_execution_agent_logs,
    get_execution_event_store,
)

router = APIRouter(prefix="/execution", tags=["execution"])


def _status_from_entries(entries: list[tuple[str, str, str]]) -> str:
    if any(tag == "agent_response" for tag, _, _ in entries):
        return "completed"
    if entries:
        return "running"
    return "unknown"


def _has_error(entries: list[tuple[str, str, str]]) -> bool:
    for tag, _, payload in entries:
        text = payload.lower()
        if tag == "agent_response" and text.startswith("error:"):
            return True
        if (
            "failed" in text
            or '"status": "error"' in text
            or "'status': 'error'" in text
        ):
            return True
    return False


@router.get("/agents")
def execution_agents() -> dict[str, object]:
    runs = execution_runs()["runs"]
    if runs:
        return {
            "runs": runs,
            "agents": [_run_to_agent_compat(run) for run in runs],
        }

    logs = get_execution_agent_logs()
    agents: list[dict[str, object]] = []

    for agent_name in logs.list_agents():
        entries = logs.load_recent(agent_name, limit=12)
        latest_tag, latest_at, latest_payload = entries[-1] if entries else ("", "", "")
        error = _has_error(entries)
        agents.append(
            {
                "agent_name": agent_name,
                "title": agent_name,
                "status": "error" if error else _status_from_entries(entries),
                "ok": not error,
                "latest_tag": latest_tag,
                "latest_at": latest_at,
                "latest": latest_payload,
                "entries": [
                    {"type": tag, "timestamp": timestamp, "text": payload}
                    for tag, timestamp, payload in entries
                ],
            }
        )

    agents.sort(key=lambda agent: str(agent.get("latest_at") or ""), reverse=True)
    return {"agents": agents}


@router.get("/runs")
def execution_runs(limit: int = 30) -> dict[str, list[ExecutionRun]]:
    return {"runs": get_execution_event_store().list_runs(limit=limit)}


@router.get("/runs/{request_id}/stream")
def execution_run_stream(
    request_id: str,
    after_id: Annotated[int, Query(alias="afterId")] = 0,
) -> StreamingResponse:
    store = get_execution_event_store()
    workspace_id = require_current_workspace()

    async def event_stream() -> AsyncIterator[str]:
        subscription = store.subscribe(
            workspace_id=workspace_id, request_ids={request_id}
        )
        try:
            run = store.get_run(request_id)
            if run is None:
                yield ui_stream.sse_part(
                    ui_stream.error_part("Execution run not found")
                )
                yield ui_stream.sse_part(ui_stream.finish_message())
                yield ui_stream.DONE
                return

            yield ui_stream.sse_part(ui_stream.start_message(f"execution-{request_id}"))
            terminal = False
            for event in store.list_events(request_id, after_id=after_id):
                payload = _execution_event_payload(workspace_id, run, event)
                async for chunk in _stream_execution_event_payload(
                    payload, generate_interaction=False
                ):
                    yield chunk
                if _is_terminal_state(event["state"]):
                    terminal = True

            if terminal or _is_terminal_status(run["status"]):
                yield ui_stream.sse_part(ui_stream.finish_message())
                yield ui_stream.DONE
                return

            while True:
                try:
                    payload = await asyncio.wait_for(
                        subscription.queue.get(), timeout=25.0
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                async for chunk in _stream_execution_event_payload(
                    payload, generate_interaction=True
                ):
                    yield chunk
                if _is_terminal_state(payload["event"]["state"]):
                    yield ui_stream.sse_part(ui_stream.finish_message())
                    yield ui_stream.DONE
                    return
        finally:
            store.unsubscribe(subscription)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "cache-control": "no-cache",
        },
    )


async def _stream_execution_event_payload(
    payload: ExecutionEventPayload, *, generate_interaction: bool
) -> AsyncIterator[str]:
    yield ui_stream.sse_part(ui_stream.data_agent_event(payload))
    yield ui_stream.sse_part(ui_stream.data_execution_event(payload))
    if not generate_interaction:
        return
    async for text_chunk in _agent_response_text_chunks(payload):
        yield text_chunk


def _execution_event_payload(
    workspace_id: str, run: ExecutionRun, event: ExecutionEvent
) -> ExecutionEventPayload:
    return {
        "workspaceId": workspace_id,
        "runId": run["runId"],
        "requestId": run["requestId"],
        "memoryId": run["memoryId"],
        "threadId": run["threadId"],
        "parentMemoryId": run["parentMemoryId"],
        "parentRunId": run["parentRunId"],
        "scope": run["scope"],
        "title": run["title"],
        "event": event,
    }


def _is_terminal_state(state: object) -> bool:
    return state in {"completed", "failed"}


def _is_terminal_status(status: object) -> bool:
    return status in {"completed", "failed"}


async def _agent_response_text_chunks(
    payload: ExecutionEventPayload,
) -> AsyncIterator[str]:
    event = payload["event"]
    if event["type"] not in {"agent-response", "message.created"} or not isinstance(
        event["text"], str
    ):
        return
    text = event["text"].strip()
    if not text:
        return
    result = await InteractionAgentRuntime().handle_agent_message(
        _format_execution_payload_for_interaction(payload)
    )
    if not result.success or not result.response.strip():
        return
    text_part_id = f"text-execution-{uuid.uuid4()}"
    yield ui_stream.sse_part(ui_stream.text_start(text_part_id))
    yield ui_stream.sse_part(
        ui_stream.text_delta(text_part_id, result.response.strip())
    )
    yield ui_stream.sse_part(ui_stream.text_end(text_part_id))


def _format_execution_payload_for_interaction(payload: ExecutionEventPayload) -> str:
    event = payload["event"]
    state = str(event["state"] or "")
    ok = state != "output-error"
    status = "SUCCESS" if ok else "FAILED"
    memory_id = payload["memoryId"]
    title = payload["title"] or memory_id
    request_id = payload["requestId"]
    text = str(event["text"] or "").strip()
    error = str(event["error"] or "").strip()
    error_line = f"\nerror: {error}" if error else ""
    return f"[{status}] {memory_id} / {title}: {text}\nrequest_id: {request_id}{error_line}"


def _run_to_agent_compat(run: ExecutionRun) -> dict[str, object]:
    parts = run["parts"]
    latest = parts[-1] if parts else None
    latest_text = ""
    if latest is not None:
        latest_text = str(latest["text"] or latest["error"] or "")
    return {
        "agent_name": run["memoryId"],
        "title": run["title"],
        "status": run["status"],
        "ok": run["ok"] is not False,
        "latest_tag": latest["type"] if latest is not None else "",
        "latest_at": latest["createdAt"] if latest is not None else run["updatedAt"],
        "latest": latest_text,
        "entries": [
            {
                "type": part["type"],
                "timestamp": part["createdAt"],
                "text": part["text"] or part["error"] or part["toolName"] or "",
            }
            for part in parts
        ],
        "parts": parts,
        "requestId": run["requestId"],
        "runId": run["runId"],
        "memoryId": run["memoryId"],
        "parentMemoryId": run["parentMemoryId"],
        "parentRunId": run["parentRunId"],
        "scope": run["scope"],
    }


__all__ = ["router"]
