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
from ...services.gmail.client import resolve_workspace_gmail_user_id
from ...services.memory import MemorySearchResult, get_memory_store
from ..tool_schemas import TOOL_SCHEMAS as CATALOG_SCHEMAS

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


class _DraftAttachmentArgs(TypedDict, total=False):
    name: str
    mimetype: str | None
    s3key: str | None


class _SendDraftArgs(TypedDict, total=False):
    to: str
    subject: str
    body: str
    cc: list[str] | None
    bcc: list[str] | None
    extra_recipients: list[str] | None
    is_html: bool | None
    thread_id: str | None
    draft_id: str | None
    attachment: _DraftAttachmentArgs | None


class _WaitArgs(TypedDict):
    reason: str


class _CancelExecutionArgs(TypedDict, total=False):
    memory_id: Required[str]
    reason: str


class _SendFollowupArgs(TypedDict):
    memory_id: str
    message: str


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
            # Parameters come from the web catalog's Zod schema, converted
            # via apps/web/scripts/generate-tool-schemas.ts.
            "parameters": cast(_JsonObject, CATALOG_SCHEMAS["send_draft"]),
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
    {
        "type": "function",
        "function": {
            "name": "send_followup_to_agent",
            "description": (
                "Add a clarification, constraint, or amendment to an already-"
                "running execution agent WITHOUT cancelling its progress. The "
                "running agent will pick up the follow-up at its next iteration "
                "boundary. Only valid for memory_id values currently in "
                "<active_execution_runs>. Use this for refinements like "
                "'also exclude X', 'make sure to include Y', or 'use template Z' "
                "— do NOT use it to start unrelated tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "memory_id of the in-flight task to amend. MUST appear in <active_execution_runs>.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The amendment / clarification, written for the agent (not the user).",
                    },
                },
                "required": ["memory_id", "message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_execution",
            "description": (
                "Stop an in-flight execution agent. Only valid for memory_id values "
                "currently listed in <in_flight>. Returns whether cancellation was "
                "effective (the task was alive and got the signal) or arrived too "
                "late (task already finished). Never call speculatively — only on "
                "explicit user request to stop / cancel / nevermind an ongoing task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "memory_id of the in-flight task to cancel. MUST appear in <in_flight>.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Short user-facing reason for the cancellation (logged with the event).",
                    },
                },
                "required": ["memory_id"],
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
    google_error = _google_preflight_error(
        instructions=instructions, task_name=task_name
    )
    if google_error:
        return ToolResult(
            success=False,
            payload={"error": google_error, "status": "not_submitted"},
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


_GOOGLE_INTENT_TERMS: tuple[str, ...] = (
    # Gmail
    "gmail",
    "email",
    "emails",
    "inbox",
    "mail",
    "mailbox",
    "reply",
    "forward",
    "draft",
    # Calendar
    "calendar",
    "gcal",
    "schedule",
    "meeting",
    "event",
    "invite",
    "availability",
    # Drive / Docs / Sheets / Slides
    "drive",
    "doc",
    "docs",
    "document",
    "sheet",
    "sheets",
    "spreadsheet",
    "slides",
    "presentation",
    # Contacts
    "contact",
    "contacts",
    # Catch-all
    "google",
)


def _google_preflight_error(
    *, instructions: str, task_name: str | None = None
) -> str | None:
    """Return a connect-google error if the request needs Google but none is connected.

    Triggers on any Google-service keyword (gmail, calendar, drive, docs, contacts,
    or a bare "google" mention). The frontend matches the canned text to surface
    the inline Connect Google button — see
    apps/web/src/features/assistant/components/catalog/components/integrations/utils.ts.
    """
    text = f"{task_name or ''} {instructions or ''}".lower()
    if not any(term in text for term in _GOOGLE_INTENT_TERMS):
        return None
    if resolve_workspace_gmail_user_id():
        return None
    return (
        "Google is not currently connected to your account. Please connect Google "
        "in settings first, then I can help."
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
        google_error = _google_preflight_error(
            instructions=instructions, task_name=task_name
        )
        if google_error:
            return ToolResult(
                success=False,
                payload={
                    "error": google_error,
                    "status": "not_submitted",
                    "item": index,
                },
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
    # Register with the task registry so cancel_execution can target this
    # request_id later. Done callbacks are independent — both fire.
    from ..execution_agent.task_registry import get_task_registry

    get_task_registry().register(request_id, task)
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
            if part["type"] == "status" and part["state"] == "queued":
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


# Register an email draft for the UI without producing user-visible chat text
def send_draft(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    extra_recipients: list[str] | None = None,
    is_html: bool | None = None,
    thread_id: str | None = None,
    draft_id: str | None = None,
    attachment: _DraftAttachmentArgs | None = None,
) -> ToolResult:
    """Register a draft in transcript-only memory; the UI renders it from tool-call args."""
    log = get_conversation_log()

    log.record_draft(to, subject, body)
    logger.info(f"Draft recorded for: {to}")

    return ToolResult(
        success=True,
        payload={
            "status": "draft_recorded",
            "to": to,
            "subject": subject,
            "cc": cc or [],
            "bcc": bcc or [],
            "extra_recipients": extra_recipients or [],
            "is_html": is_html,
            "thread_id": thread_id,
            "draft_id": draft_id,
            "attachment": attachment,
        },
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


def send_followup_to_agent(memory_id: str, message: str) -> ToolResult:
    """Push a follow-up message to a running execution agent's inbox.

    Used for non-destructive refinement (extra constraint, clarification)
    of an already-running task. The execution-agent loop drains its inbox
    at iteration boundaries and treats messages as user follow-ups.

    Returns:
        - {"status": "dispatched", "request_ids": [...], "count": N}
          when at least one live task received the follow-up
        - {"status": "too_late", "memory_id": ...}
          when no live task matched
    """
    from ..execution_agent.task_registry import get_task_registry

    store = get_execution_event_store()
    registry = get_task_registry()

    active: list[str] = []
    for run in store.list_runs(limit=100):
        if run.get("memoryId") != memory_id:
            continue
        if run.get("status") in {"completed", "failed"}:
            continue
        request_id = str(run.get("requestId") or "")
        if request_id and registry.has(request_id):
            active.append(request_id)

    if not active:
        return ToolResult(
            success=True,
            payload={
                "status": "too_late",
                "memory_id": memory_id,
                "message": (
                    "No in-flight task found for that memory_id — it may have "
                    "already finished. If the user's amendment is still "
                    "relevant, dispatch it as a new send_message_to_agent."
                ),
            },
        )

    dispatched: list[str] = []
    for request_id in active:
        if registry.push_followup(request_id, message):
            dispatched.append(request_id)
            store.record_event(
                request_id=request_id,
                memory_id=memory_id,
                event_type="status",
                state="running",
                text=f"follow-up dispatched: {message}",
            )

    return ToolResult(
        success=True,
        payload={
            "status": "dispatched" if dispatched else "too_late",
            "memory_id": memory_id,
            "request_ids": dispatched,
            "count": len(dispatched),
        },
    )


def cancel_execution(memory_id: str, reason: str = "") -> ToolResult:
    """Stop an in-flight execution by memory_id.

    Resolves memory_id to one or more active request_ids via the execution
    event store, then asks the task registry to cancel each matching task.
    The actual cancellation flows asynchronously: the execution runtime
    catches CancelledError, records a terminal run.failed event with
    text=cancelled, and the SSE pipelines surface that to the UI.

    Returns:
        - {"status": "cancelled", "request_ids": [...], "count": N}
          when at least one live task was signalled
        - {"status": "too_late", "memory_id": ...}
          when no live task matched (either unknown memory_id, or all runs
          for that memory had already finished)
    """
    from ..execution_agent.task_registry import get_task_registry

    store = get_execution_event_store()
    registry = get_task_registry()

    # Find non-terminal runs for this memory_id. Limited to recent runs to
    # avoid pathological scans on long-lived memories.
    active: list[str] = []
    for run in store.list_runs(limit=100):
        if run.get("memoryId") != memory_id:
            continue
        if run.get("status") in {"completed", "failed"}:
            continue
        request_id = str(run.get("requestId") or "")
        if request_id and registry.has(request_id):
            active.append(request_id)

    if not active:
        return ToolResult(
            success=True,
            payload={
                "status": "too_late",
                "memory_id": memory_id,
                "reason": reason,
                "message": (
                    "No in-flight task found for that memory_id — it may have "
                    "already finished. Check the latest result before assuming "
                    "the work didn't happen."
                ),
            },
        )

    cancelled: list[str] = []
    for request_id in active:
        if registry.cancel(request_id):
            cancelled.append(request_id)

    return ToolResult(
        success=True,
        payload={
            "status": "cancelled" if cancelled else "too_late",
            "memory_id": memory_id,
            "request_ids": cancelled,
            "count": len(cancelled),
            "reason": reason,
        },
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
            for field in ("cc", "bcc", "extra_recipients"):
                if field in args and args[field] is not None and not isinstance(args[field], list):
                    return _invalid_argument(field)
            if "is_html" in args and args["is_html"] is not None and not isinstance(args["is_html"], bool):
                return _invalid_argument("is_html")
            for field in ("thread_id", "draft_id"):
                if field in args and args[field] is not None and not isinstance(args[field], str):
                    return _invalid_argument(field)
            if "attachment" in args and args["attachment"] is not None and not isinstance(args["attachment"], dict):
                return _invalid_argument("attachment")
            return send_draft(**cast(_SendDraftArgs, cast(object, args)))
        if name == "wait":
            error = _validate_required(args, {"reason": str})
            if error:
                return error
            return wait(**cast(_WaitArgs, cast(object, args)))
        if name == "cancel_execution":
            error = _validate_required(args, {"memory_id": str})
            if error:
                return error
            return cancel_execution(**cast(_CancelExecutionArgs, cast(object, args)))
        if name == "send_followup_to_agent":
            error = _validate_required(args, {"memory_id": str, "message": str})
            if error:
                return error
            return send_followup_to_agent(
                **cast(_SendFollowupArgs, cast(object, args))
            )

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
