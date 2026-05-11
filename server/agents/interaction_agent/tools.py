"""Tool definitions for interaction agent."""

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from ...logging_config import logger
from ...services.conversation import get_conversation_log
from ...services.execution import get_execution_agent_logs
from ...services.memory import MemorySearchResult, get_memory_store
from ..execution_agent.batch_manager import ExecutionBatchManager


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False

# Tool schemas for OpenRouter
TOOL_SCHEMAS = [
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
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["instructions"],
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

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()


# Create or reuse memory context and dispatch instructions asynchronously
def send_message_to_agent(
    instructions: str,
    memory_id: Optional[str] = None,
    task_name: Optional[str] = None,
) -> ToolResult:
    """Send instructions to an execution worker using a memory context."""
    memory_store = get_memory_store()
    request_id = str(uuid.uuid4())
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

    get_execution_agent_logs().record_request(memory.memory_id, instructions)
    memory_store.record_event(
        type="execution_request",
        text=instructions,
        memory_id=memory.memory_id,
        idempotency_key=f"execution_request:{request_id}",
        source="interaction_agent",
        metadata={"request_id": request_id, "task_name": task_name},
    )

    action = "Created memory and submitted" if is_new else "Submitted with memory"
    logger.info(f"{action}: {memory.memory_id} ({memory.title})")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(
                memory.memory_id,
                instructions,
                memory_title=memory.title,
                request_id=request_id,
            )
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Memory '{memory.memory_id}' execution completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Memory '{memory.memory_id}' execution failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return ToolResult(success=False, payload={"error": "No event loop available"})

    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "memory_id": memory.memory_id,
            "memory_title": memory.title,
            "new_memory_created": is_new,
        },
    )


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
def get_tool_schemas():
    """Return OpenAI-compatible tool schemas."""
    return TOOL_SCHEMAS


# Route tool calls to appropriate handlers with argument validation and error handling
def handle_tool_call(name: str, arguments: Any) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        if name == "send_message_to_agent":
            return send_message_to_agent(**args)
        if name == "search_memory":
            return search_memory(**args)
        if name == "send_message_to_user":
            return send_message_to_user(**args)
        if name == "send_draft":
            return send_draft(**args)
        if name == "wait":
            return wait(**args)

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})


def _serialize_memory_result(result: MemorySearchResult) -> dict[str, Any]:
    memory = result.memory
    return {
        "memory_id": memory.memory_id,
        "kind": memory.kind,
        "title": memory.title,
        "summary": memory.summary,
        "score": result.score,
        "confidence": result.confidence,
        "reason": result.reason,
        "links": [
            {"kind": link.kind, "value": link.value, "label": link.label}
            for link in memory.links[:12]
        ],
        "recent_events": [
            {
                "type": event.type,
                "timestamp": event.timestamp or event.recorded_at,
                "text": event.text,
            }
            for event in memory.recent_events[-5:]
        ],
    }
