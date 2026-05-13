"""Tool definitions for interaction agent."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Required, TypeAlias, TypedDict, cast

from ...logging_config import logger
from ...services.conversation import get_conversation_log
from ...services.execution import (
    ExecutionRun,
    get_execution_agent_logs,
    get_execution_event_store,
)
from ...services.gmail.client import get_active_gmail_user_id
from ...services.memory import MemorySearchResult, get_memory_store

if TYPE_CHECKING:
    from ..execution_agent.batch_manager import ExecutionBatchManager

_JsonValue: TypeAlias = (
    str | int | float | bool | None | list["_JsonValue"] | dict[str, "_JsonValue"]
)
_JsonObject: TypeAlias = dict[str, _JsonValue]


class _SendMessageToAgentArgs(TypedDict, total=False):
    instructions: Required[str]
    memory_id: str | None
    task_name: str | None


class _SendMessagesToAgentsArgs(TypedDict, total=False):
    items: Required[Sequence[Mapping[str, object]]]
    parent_memory_id: str | None
    coordination_note: str | None


class _SearchMemoryArgs(TypedDict, total=False):
    query: Required[str]
    limit: int


class _SendMessageToUserArgs(TypedDict):
    message: str


class _SendDraftArgs(TypedDict):
    to: str
    subject: str
    body: str


class _WaitArgs(TypedDict):
    reason: str


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: object | None = None
    user_message: str | None = None
    recorded_reply: bool = False


# Tool schemas for OpenRouter
TOOL_SCHEMAS: list[_JsonObject] = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to an execution worker using a memory context. Reuse by memory_id from <relevant_memories> or search_memory results. Create a new memory context with task_name when no memory fits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "Existing memory id to use as execution context. Use this for reuse.",
                    },
                    "task_name": {
                        "type": "string",
                        "description": "Short title for a new memory context when no existing memory fits.",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Instructions for the agent to execute.",
                    },
                },
                "required": ["instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_messages_to_agents",
            "description": "Submit multiple independent execution items at once. Use this when items can succeed or fail independently, especially different email recipients, Gmail threads, files, accounts, or unrelated workflows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_memory_id": {
                        "type": "string",
                        "description": "Optional coordinator memory id to link child tasks under.",
                    },
                    "coordination_note": {
                        "type": "string",
                        "description": "Short note/title describing the overall batch.",
                    },
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "memory_id": {
                                    "type": "string",
                                    "description": "Optional existing memory id for this independent item.",
                                },
                                "task_name": {
                                    "type": "string",
                                    "description": "Short title for this independent item when creating a child memory.",
                                },
                                "instructions": {
                                    "type": "string",
                                    "description": "Instructions for this independent item.",
                                },
                            },
                            "required": ["task_name", "instructions"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search hidden memory contexts when <relevant_memories> does not contain a fitting context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query for prior memory contexts, emails, threads, people, or tasks.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memory matches to return.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_user",
            "description": "Deliver a natural-language response directly to the user. Use this for updates, confirmations, or any assistant response the user should see immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain-text message that will be shown to the user and recorded in the conversation log.",
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_draft",
            "description": "Record an email draft so the user can review the exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email for the draft.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject for the draft.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content (plain text).",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait silently when a message is already in conversation history to avoid duplicating responses. Adds a <wait> log entry that is not visible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why waiting (e.g., 'Message already sent', 'Draft already created').",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

_execution_batch_manager: ExecutionBatchManager | None = None
_running_tasks: set[asyncio.Task[None]] = set()


def _get_execution_batch_manager() -> ExecutionBatchManager:
    global _execution_batch_manager
    if _execution_batch_manager is None:
        from ..execution_agent.batch_manager import ExecutionBatchManager

        _execution_batch_manager = ExecutionBatchManager()
    return _execution_batch_manager


# Create or reuse memory context and dispatch instructions asynchronously
def send_message_to_agent(
    instructions: str,
    memory_id: str | None = None,
    task_name: str | None = None,
) -> ToolResult:
    """Send instructions to an execution worker using a memory context."""
    gmail_error = _gmail_preflight_error(instructions=instructions, task_name=task_name)
    if gmail_error:
        get_conversation_log().record_reply(gmail_error)
        return ToolResult(
            success=False,
            payload={"error": gmail_error, "status": "not_submitted"},
            user_message=gmail_error,
            recorded_reply=True,
        )

    memory_store = get_memory_store()
    is_new = False

    if memory_id:
        memory = memory_store.get_memory(memory_id)
        if memory is None:
            return ToolResult(
                success=False,
                payload={"error": f"Unknown memory_id: {memory_id}"},
            )
    else:
        title = (task_name or instructions[:80] or "Untitled task").strip()
        memory = memory_store.create_memory(
            kind="user_task",
            title=title,
            summary=f"Task context for: {title}",
            metadata={"source": "interaction_agent"},
        )
        memory_id = memory.memory_id
        is_new = True

    active_run = _find_active_execution_run(
        memory_id=memory.memory_id,
        title=task_name or memory.title,
        instructions=instructions,
    )
    if active_run is not None:
        return ToolResult(
            success=True,
            payload=_already_in_progress_payload(active_run),
        )

    request_id = str(uuid.uuid4())
    action = "Created memory and submitted" if is_new else "Submitted with memory"
    logger.info(f"{action}: {memory.memory_id} ({memory.title})")

    submit_result = _record_and_submit_execution(
        memory_id=memory.memory_id,
        memory_title=memory.title,
        instructions=instructions,
        request_id=request_id,
        task_name=task_name,
        notify_user=False,
    )
    if not submit_result.success:
        return submit_result

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "request_id": request_id,
            "memory_id": memory.memory_id,
            "memory_title": memory.title,
            "new_memory_created": is_new,
        },
    )


def _gmail_preflight_error(
    *, instructions: str, task_name: str | None = None
) -> str | None:
    text = f"{task_name or ''} {instructions or ''}".lower()
    gmail_terms = ("gmail", "email", "emails", "inbox")
    if not any(term in text for term in gmail_terms):
        return None
    if get_active_gmail_user_id():
        return None
    return (
        "Gmail is not currently connected to your account. Please connect Gmail in "
        "settings first, then I can help with Gmail."
    )


def send_messages_to_agents(
    items: Sequence[Mapping[str, object]],
    parent_memory_id: str | None = None,
    coordination_note: str | None = None,
) -> ToolResult:
    """Submit independent work items as separate child execution memories."""
    if not items:
        return ToolResult(success=False, payload={"error": "items must not be empty"})

    memory_store = get_memory_store()
    parent_is_new = False
    parent_memory = None
    parent_title = (coordination_note or "Coordinated task").strip()

    if parent_memory_id:
        parent_memory = memory_store.get_memory(parent_memory_id)
        if parent_memory is None:
            return ToolResult(
                success=False,
                payload={"error": f"Unknown parent_memory_id: {parent_memory_id}"},
            )
    else:
        parent_memory = memory_store.create_memory(
            kind="user_task",
            title=parent_title,
            summary=f"Coordinator context for: {parent_title}",
            metadata={"source": "interaction_agent", "role": "fanout_parent"},
        )
        parent_memory_id = parent_memory.memory_id
        parent_is_new = True

    if coordination_note:
        _ = memory_store.record_event(
            type="coordination_note",
            text=coordination_note,
            memory_id=parent_memory.memory_id,
            source="interaction_agent",
            metadata={"submitted_count": len(items)},
        )

    submitted: list[dict[str, object]] = []
    for index, item in enumerate(items, start=1):
        instructions = str(item.get("instructions") or "").strip()
        task_name = str(item.get("task_name") or "").strip()
        item_memory_id = item.get("memory_id")
        if not instructions:
            return ToolResult(
                success=False,
                payload={"error": f"Item {index} is missing instructions"},
            )
        if not task_name and not item_memory_id:
            return ToolResult(
                success=False,
                payload={"error": f"Item {index} is missing task_name"},
            )
        gmail_error = _gmail_preflight_error(
            instructions=instructions, task_name=task_name
        )
        if gmail_error:
            get_conversation_log().record_reply(gmail_error)
            return ToolResult(
                success=False,
                payload={
                    "error": gmail_error,
                    "status": "not_submitted",
                    "item": index,
                },
                user_message=gmail_error,
                recorded_reply=True,
            )

        if item_memory_id:
            child_memory = memory_store.get_memory(str(item_memory_id))
            if child_memory is None:
                return ToolResult(
                    success=False,
                    payload={
                        "error": f"Unknown memory_id for item {index}: {item_memory_id}"
                    },
                )
        else:
            child_memory = memory_store.create_memory(
                kind="user_task",
                title=task_name,
                summary=f"Independent execution context for: {task_name}",
                metadata={
                    "source": "interaction_agent",
                    "role": "fanout_child",
                    "parent_memory_id": parent_memory.memory_id,
                },
            )

        memory_store.add_links(
            parent_memory.memory_id,
            [
                {
                    "kind": "child_memory",
                    "value": child_memory.memory_id,
                    "label": child_memory.title,
                }
            ],
        )

        active_run = _find_active_execution_run(
            memory_id=child_memory.memory_id,
            title=task_name or child_memory.title,
            instructions=instructions,
        )
        if active_run is not None:
            submitted.append(_already_in_progress_payload(active_run))
            continue

        request_id = str(uuid.uuid4())
        submit_result = _record_and_submit_execution(
            memory_id=child_memory.memory_id,
            memory_title=child_memory.title,
            instructions=instructions,
            request_id=request_id,
            task_name=task_name or child_memory.title,
            parent_memory_id=parent_memory.memory_id,
            notify_user=False,
        )
        if not submit_result.success:
            return submit_result

        submitted.append(
            {
                "status": "submitted",
                "request_id": request_id,
                "memory_id": child_memory.memory_id,
                "memory_title": child_memory.title,
            }
        )

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "parent_memory_id": parent_memory.memory_id,
            "parent_memory_title": parent_memory.title,
            "parent_memory_created": parent_is_new,
            "submitted_count": len(submitted),
            "children": submitted,
        },
    )


def _record_and_submit_execution(
    *,
    memory_id: str,
    memory_title: str,
    instructions: str,
    request_id: str,
    task_name: str | None = None,
    parent_memory_id: str | None = None,
    notify_user: bool = True,
) -> ToolResult:
    memory_store = get_memory_store()
    get_execution_agent_logs().record_request(memory_id, instructions)
    get_execution_event_store().record_submitted(
        request_id=request_id,
        memory_id=memory_id,
        title=memory_title,
        instructions=instructions,
        parent_memory_id=parent_memory_id,
    )
    _ = memory_store.record_event(
        type="execution_request",
        text=instructions,
        memory_id=memory_id,
        idempotency_key=f"execution_request:{request_id}",
        source="interaction_agent",
        metadata={
            "request_id": request_id,
            "task_name": task_name,
            "parent_memory_id": parent_memory_id,
        },
    )

    async def _execute_async() -> None:
        try:
            result = await _get_execution_batch_manager().execute_agent(
                memory_id,
                instructions,
                memory_title=memory_title,
                request_id=request_id,
                notify_user=notify_user,
            )
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Memory '{memory_id}' execution completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Memory '{memory_id}' execution failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return ToolResult(success=False, payload={"error": "No event loop available"})

    task = loop.create_task(_execute_async())
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
    return ToolResult(success=True, payload={"status": "submitted"})


def _find_active_execution_run(
    *,
    memory_id: str,
    title: str | None,
    instructions: str,
) -> ExecutionRun | None:
    normalized_title = _normalize_task_text(title or "")
    normalized_instructions = _normalize_task_text(instructions)
    for run in get_execution_event_store().list_runs(limit=100):
        if run.get("status") not in {"queued", "running"}:
            continue
        if run.get("memoryId") == memory_id:
            return run
        run_title = _normalize_task_text(str(run.get("title") or ""))
        if normalized_title and run_title and normalized_title == run_title:
            return run
        parts = run["parts"]
        submitted_text = ""
        for part in parts:
            if (
                part["type"] == "status"
                and part["state"] == "queued"
            ):
                submitted_text = str(part["text"] or "")
                break
        normalized_submitted = _normalize_task_text(submitted_text)
        if (
            normalized_instructions
            and normalized_submitted
            and (
                normalized_instructions == normalized_submitted
                or normalized_instructions in normalized_submitted
                or normalized_submitted in normalized_instructions
            )
        ):
            return run
    return None


def _already_in_progress_payload(run: ExecutionRun) -> dict[str, object]:
    return {
        "status": "already_in_progress",
        "request_id": run.get("requestId"),
        "memory_id": run.get("memoryId"),
        "memory_title": run.get("title"),
    }


def _normalize_task_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def search_memory(query: str, limit: int = 8) -> ToolResult:
    """Search memory contexts not already visible in the prompt."""
    results = get_memory_store().search(
        query,
        limit=max(1, min(limit or 8, 20)),
        context="search_memory_tool",
    )
    return ToolResult(
        success=True,
        payload={
            "matches": [_serialize_memory_result(result) for result in results],
        },
    )


# Send immediate message to user and record in conversation history
def send_message_to_user(message: str) -> ToolResult:
    """Record a user-visible reply in the conversation log."""
    log = get_conversation_log()
    log.record_reply(message)

    return ToolResult(
        success=True,
        payload={"status": "delivered"},
        user_message=message,
        recorded_reply=True,
    )


# Format and record email draft for user review
def send_draft(
    to: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()

    message = f"To: {to}\nSubject: {subject}\n\n{body}"

    log.record_reply(message)
    logger.info(f"Draft recorded for: {to}")

    return ToolResult(
        success=True,
        payload={
            "status": "draft_recorded",
            "to": to,
            "subject": subject,
        },
        user_message=message,
        recorded_reply=True,
    )


# Record silent wait state to avoid duplicate responses
def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()

    # Record a dedicated wait entry so the UI knows to ignore it
    log.record_wait(reason)

    return ToolResult(
        success=True,
        payload={
            "status": "waiting",
            "reason": reason,
        },
        recorded_reply=True,
    )


# Return predefined tool schemas for LLM function calling
def get_tool_schemas() -> list[_JsonObject]:
    """Return OpenAI-compatible tool schemas."""
    return TOOL_SCHEMAS


# Route tool calls to appropriate handlers with argument validation and error handling
def handle_tool_call(name: str, arguments: object) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = cast(
                dict[str, object],
                json.loads(arguments) if arguments.strip() else {},
            )
        elif isinstance(arguments, dict):
            args = cast(dict[str, object], arguments)
        else:
            return ToolResult(
                success=False, payload={"error": "Invalid arguments format"}
            )

        if name == "send_message_to_agent":
            error = _validate_required(args, {"instructions": str})
            if error:
                return error
            return send_message_to_agent(
                **cast(_SendMessageToAgentArgs, cast(object, args))
            )
        if name == "send_messages_to_agents":
            error = _validate_required(args, {"items": list})
            if error:
                return error
            return send_messages_to_agents(
                **cast(_SendMessagesToAgentsArgs, cast(object, args))
            )
        if name == "search_memory":
            error = _validate_required(args, {"query": str})
            if error:
                return error
            if "limit" in args and not isinstance(args["limit"], int):
                return _invalid_argument("limit")
            return search_memory(**cast(_SearchMemoryArgs, cast(object, args)))
        if name == "send_message_to_user":
            error = _validate_required(args, {"message": str})
            if error:
                return error
            return send_message_to_user(
                **cast(_SendMessageToUserArgs, cast(object, args))
            )
        if name == "send_draft":
            error = _validate_required(args, {"to": str, "subject": str, "body": str})
            if error:
                return error
            return send_draft(**cast(_SendDraftArgs, cast(object, args)))
        if name == "wait":
            error = _validate_required(args, {"reason": str})
            if error:
                return error
            return wait(**cast(_WaitArgs, cast(object, args)))

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(
            success=False, payload={"error": f"Missing required arguments: {exc}"}
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})


def _validate_required(
    args: Mapping[str, object],
    required: Mapping[str, type],
) -> ToolResult | None:
    for field, expected_type in required.items():
        if field not in args or not isinstance(args[field], expected_type):
            return _invalid_argument(field)
    return None


def _invalid_argument(field: str) -> ToolResult:
    return ToolResult(
        success=False,
        payload={"error": f"Missing or invalid arguments: {field}"},
    )


def _serialize_memory_result(result: MemorySearchResult) -> dict[str, object]:
    memory = result.memory
    return {
        "memory_id": memory.memory_id,
        "kind": memory.kind,
        "title": memory.title,
        "summary": memory.summary,
        "score": result.score,
        "confidence": result.confidence,
        "reason": result.reason,
        "ranking_reason": result.reason,
        "links": [
            {"kind": link.kind, "value": link.value, "label": link.label}
            for link in memory.links[:12]
        ],
        "matched_events": [
            {
                "event_id": event.event_id,
                "type": event.type,
                "timestamp": event.timestamp or event.recorded_at,
                "text": event.text,
            }
            for event in memory.recent_events[:3]
        ],
        "recent_events": [
            {
                "event_id": event.event_id,
                "type": event.type,
                "timestamp": event.timestamp or event.recorded_at,
                "text": event.text,
            }
            for event in memory.recent_events[-5:]
        ],
    }
