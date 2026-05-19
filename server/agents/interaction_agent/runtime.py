"""Interaction Agent Runtime - handles LLM calls for user and agent turns."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, cast

from ...config import Settings, get_settings
from ...core.workspace_context import require_current_workspace
from ...db.threads import (
    ThreadNotFoundError,
    get_thread_repository,
)
from ...logging_config import logger
from ...openrouter_client.client import (
    JsonObject,
    JsonValue,
    OpenRouterAssistantMessage,
    OpenRouterChatCompletion,
    OpenRouterChatCompletionChunk,
    OpenRouterToolCall,
    request_chat_completion,
    stream_chat_completion,
)
from ...services.conversation import ui_stream
from ...services.conversation.log import ConversationLog, get_conversation_log
from ...services.conversation.summarization.working_memory_log import (
    WorkingMemoryLog,
    get_working_memory_log,
)
from ...services.gmail.llm_payload import shrink_gmail_tool_result
from ...services.execution import (
    ExecutionEventPayload,
    ExecutionEventSubscription,
    get_execution_event_store,
)
from ...utils.timezones import now_in_user_timezone
from ..tool_schemas import MAX_VALIDATION_RETRIES_PER_TOOL, validate_tool_args
from .agent import build_system_prompt, prepare_message_with_history
from .tools import ToolResult, get_tool_schemas, handle_tool_call

ChatMessagePayload = dict[str, object]
ToolArguments = dict[str, JsonValue]

_MSG_TOOL = "send_message_to_user"
_MSG_JSON_PREFIX = '{"message": "'
_MSG_JSON_SUFFIX = '"}'


def _unescape_json_str(fragment: str) -> str:
    """Unescape JSON string escape sequences in a stream fragment."""
    out: list[str] = []
    i = 0
    while i < len(fragment):
        if fragment[i] == "\\" and i + 1 < len(fragment):
            nxt = fragment[i + 1]
            if nxt == '"':
                out.append('"')
                i += 2
            elif nxt == "\\":
                out.append("\\")
                i += 2
            elif nxt == "n":
                out.append("\n")
                i += 2
            elif nxt == "t":
                out.append("\t")
                i += 2
            elif nxt == "r":
                out.append("\r")
                i += 2
            elif nxt == "/":
                out.append("/")
                i += 2
            else:
                out.append(fragment[i])
                i += 1
        else:
            out.append(fragment[i])
            i += 1
    return "".join(out)


def _mutable_messages(
    messages: Sequence[Mapping[str, str]],
) -> list[ChatMessagePayload]:
    return [dict(message) for message in messages]


@dataclass
class InteractionResult:
    """Result from the interaction agent."""

    success: bool
    response: str
    error: str | None = None
    execution_agents_used: int = 0


@dataclass
class _ToolCall:
    """Parsed tool invocation from an LLM response."""

    identifier: str | None
    name: str
    arguments: ToolArguments


@dataclass
class _LoopSummary:
    """Aggregate information produced by the interaction loop."""

    last_assistant_text: str = ""
    user_messages: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    execution_agents: set[str] = field(default_factory=set)


@dataclass
class _StreamingToolCall:
    identifier: str
    name: str = ""
    arguments: str = ""
    input_started: bool = False
    # Populated when this call is send_message_to_user and text streaming has begun
    msg_text_part_id: str | None = field(default=None, init=False)
    _msg_prefix_buf: str = field(default="", init=False, repr=False)
    _msg_prefix_done: bool = field(default=False, init=False, repr=False)
    _msg_lookahead: str = field(default="", init=False, repr=False)

    def as_openrouter(self) -> OpenRouterToolCall:
        return {
            "id": self.identifier,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }

    def feed_msg_delta(self, arg_delta: str) -> str:
        """Extract and return the visible text safe to emit now.

        Skips the JSON prefix ``{"message": "`` and keeps a 2-char lookahead
        to avoid emitting the closing ``"}`` suffix prematurely.
        """
        if not self._msg_prefix_done:
            self._msg_prefix_buf += arg_delta
            if len(self._msg_prefix_buf) < len(_MSG_JSON_PREFIX):
                return ""
            self._msg_prefix_done = True
            rest = (
                self._msg_prefix_buf[len(_MSG_JSON_PREFIX) :]
                if self._msg_prefix_buf.startswith(_MSG_JSON_PREFIX)
                else self._msg_prefix_buf  # unexpected format — pass through
            )
            self._msg_lookahead = rest
        else:
            self._msg_lookahead += arg_delta

        if len(self._msg_lookahead) <= len(_MSG_JSON_SUFFIX):
            return ""
        to_emit = self._msg_lookahead[: -len(_MSG_JSON_SUFFIX)]
        self._msg_lookahead = self._msg_lookahead[-len(_MSG_JSON_SUFFIX) :]
        return _unescape_json_str(to_emit)

    def flush_msg(self) -> str:
        """Return any remaining content after stripping the closing JSON suffix."""
        buf = self._msg_lookahead
        if buf.endswith(_MSG_JSON_SUFFIX):
            buf = buf[: -len(_MSG_JSON_SUFFIX)]
        return _unescape_json_str(buf)


class _AssistantPartsAccumulator:
    """Collect AI SDK UIMessage parts as the stream emits them.

    Each SSE chunk produced by stream_execute is parsed and folded into a
    single ordered list of consolidated parts (text/tool/data-agent-event)
    suitable for persisting into messages.parts_json. Text deltas merge
    into one text part per part-id; tool input/output rounds collapse into
    a single tool part keyed on toolCallId; data-agent-event parts are
    kept as-is. Streaming-only frames (start, finish, step boundaries,
    reasoning) are ignored — the persisted form represents the message
    as a finished artifact, not its emission timeline.
    """

    def __init__(self) -> None:
        self.parts: list[dict[str, object]] = []
        self._text_index: dict[str, int] = {}
        self._tool_index: dict[str, int] = {}

    def feed_chunk(self, sse_chunk: str) -> None:
        """Parse a single SSE chunk emitted by ui_stream.sse_part and fold it.

        Non-data chunks (heartbeats, [DONE], malformed JSON) are silently
        skipped — accumulation must never raise out of stream_execute.
        """
        if not sse_chunk.startswith("data: "):
            return
        body = sse_chunk[len("data: "):].strip()
        if not body or body == "[DONE]":
            return
        try:
            part = cast(dict[str, object], json.loads(body))
        except (json.JSONDecodeError, TypeError):
            return
        self._feed_part(part)

    def _feed_part(self, part: dict[str, object]) -> None:
        ptype = part.get("type")
        if ptype == "text-start":
            pid = self._str(part.get("id"))
            if pid is None:
                return
            self.parts.append({"type": "text", "text": ""})
            self._text_index[pid] = len(self.parts) - 1
            return
        if ptype == "text-delta":
            pid = self._str(part.get("id"))
            delta = self._str(part.get("delta")) or ""
            if pid is None:
                return
            idx = self._text_index.get(pid)
            if idx is None:
                self.parts.append({"type": "text", "text": delta})
                self._text_index[pid] = len(self.parts) - 1
                return
            existing = self.parts[idx]
            current = existing.get("text")
            existing["text"] = (
                str(current) if isinstance(current, str) else ""
            ) + delta
            return
        if ptype == "text-end":
            pid = self._str(part.get("id"))
            if pid is not None:
                _ = self._text_index.pop(pid, None)
            return
        if ptype == "tool-input-start":
            tid = self._str(part.get("toolCallId"))
            tool_name = self._str(part.get("toolName")) or "unknown"
            if tid is None:
                return
            self.parts.append(
                {
                    "type": f"tool-{tool_name}",
                    "toolCallId": tid,
                    "state": "input-streaming",
                }
            )
            self._tool_index[tid] = len(self.parts) - 1
            return
        if ptype == "tool-input-available":
            tid = self._str(part.get("toolCallId"))
            tool_name = self._str(part.get("toolName")) or "unknown"
            if tid is None:
                return
            idx = self._tool_index.get(tid)
            if idx is None:
                self.parts.append(
                    {
                        "type": f"tool-{tool_name}",
                        "toolCallId": tid,
                        "state": "input-available",
                        "input": part.get("input"),
                    }
                )
                self._tool_index[tid] = len(self.parts) - 1
                return
            entry = self.parts[idx]
            entry["state"] = "input-available"
            entry["input"] = part.get("input")
            return
        if ptype == "tool-output-available":
            tid = self._str(part.get("toolCallId"))
            if tid is None:
                return
            idx = self._tool_index.get(tid)
            if idx is None:
                # Output before input — synthesize a tool part without a name.
                self.parts.append(
                    {
                        "type": "tool-unknown",
                        "toolCallId": tid,
                        "state": "output-available",
                        "output": part.get("output"),
                    }
                )
                self._tool_index[tid] = len(self.parts) - 1
                return
            entry = self.parts[idx]
            entry["state"] = "output-available"
            entry["output"] = part.get("output")
            return
        if ptype == "data-agent-event":
            # Already in AI SDK part shape — pass through.
            self.parts.append(part)
            return
        # Ignore start/finish/start-step/finish-step/reasoning/tool-input-delta.
        # The persisted snapshot doesn't need streaming markers.

    def text_content(self) -> str:
        """Aggregate text content for the messages.content column (required NOT NULL)."""
        chunks: list[str] = []
        for entry in self.parts:
            if entry.get("type") == "text":
                value = entry.get("text")
                if isinstance(value, str):
                    chunks.append(value)
        return "".join(chunks).strip()

    @staticmethod
    def _str(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)


class InteractionAgentRuntime:
    """Manages the interaction agent's request processing."""

    MAX_TOOL_ITERATIONS: ClassVar[int] = 8

    # Initialize interaction agent runtime with settings and service dependencies
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key: str | None = settings.openrouter_api_key
        self.model: str = settings.interaction_agent_model
        self.settings: Settings = settings
        self.conversation_log: ConversationLog = get_conversation_log()
        self.working_memory_log: WorkingMemoryLog = get_working_memory_log()
        self.tool_schemas: Sequence[Mapping[str, object]] = cast(
            Sequence[Mapping[str, object]], get_tool_schemas()
        )

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
            )

    # Main entry point for processing user messages through the LLM interaction loop
    async def execute(self, user_message: str) -> InteractionResult:
        """Handle a user-authored message."""

        try:
            transcript_before = self._load_conversation_transcript()
            recent_transcript = self._load_recent_conversation_transcript()
            self.conversation_log.record_user_message(user_message)

            system_prompt = build_system_prompt()
            messages = _mutable_messages(
                prepare_message_with_history(
                    user_message,
                    transcript_before,
                    recent_transcript=recent_transcript,
                    message_type="user",
                )
            )

            logger.info("Processing user message through interaction agent")
            summary = await self._run_interaction_loop(system_prompt, messages)

            final_response = self._finalize_response(summary)

            if final_response and not summary.user_messages:
                self.conversation_log.record_reply(final_response)

            return InteractionResult(
                success=True,
                response=final_response,
                execution_agents_used=len(summary.execution_agents),
            )

        except Exception as exc:
            logger.exception(f"Interaction agent failed: {exc}")
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )

    async def stream_execute(
        self,
        user_message: str,
        *,
        thread_id: str | None = None,
        turn_index: int | None = None,
        notifications: str | None = None,
    ) -> AsyncIterator[str]:
        """Handle a user message and emit AI SDK UI Message Stream SSE parts.

        Accumulates parts into a final UIMessage shape and persists via the
        thread repository in the finally block when `thread_id` is set, so
        the assistant message survives reload.
        """

        execution_store = get_execution_event_store()
        subscription: ExecutionEventSubscription | None = None
        run_id = f"interaction-{uuid.uuid4()}"
        accumulator = _AssistantPartsAccumulator()
        completed_normally = False

        def yield_with_accum(chunk: str) -> str:
            accumulator.feed_chunk(chunk)
            return chunk

        try:
            subscription = execution_store.subscribe(request_ids=set())
            message_id = f"msg-{uuid.uuid4()}"
            yield yield_with_accum(ui_stream.sse_part(ui_stream.start_message(message_id)))
            yield yield_with_accum(
                self._agent_event_chunk(
                    run_id=run_id,
                    event_type="run.created",
                    state="queued",
                    thread_id=thread_id,
                )
            )
            yield yield_with_accum(
                self._agent_event_chunk(
                    run_id=run_id,
                    event_type="run.started",
                    state="running",
                    thread_id=thread_id,
                )
            )
            transcript_before = self._load_conversation_transcript()
            recent_transcript = self._load_recent_conversation_transcript()
            self.conversation_log.record_user_message(user_message)

            system_prompt = build_system_prompt(notifications=notifications)
            messages = _mutable_messages(
                prepare_message_with_history(
                    user_message,
                    transcript_before,
                    recent_transcript=recent_transcript,
                    message_type="user",
                )
            )

            async for chunk in self._run_streaming_interaction_loop(
                system_prompt,
                messages,
                subscription.request_ids,
                subscription,
                run_id,
            ):
                yield yield_with_accum(chunk)
        except Exception as exc:
            logger.exception(f"Streaming interaction agent failed: {exc}")
            yield yield_with_accum(
                self._agent_event_chunk(
                    run_id=run_id,
                    event_type="run.failed",
                    state="failed",
                    error=str(exc),
                )
            )
            yield yield_with_accum(ui_stream.sse_part(ui_stream.error_part(str(exc))))
        else:
            yield yield_with_accum(ui_stream.sse_part(ui_stream.finish_message()))
            yield ui_stream.DONE
            completed_normally = True
        finally:
            if subscription is not None:
                get_execution_event_store().unsubscribe(subscription)
            if thread_id is not None and accumulator.parts:
                self._persist_assistant_message(
                    thread_id, accumulator, turn_index=turn_index
                )
            if thread_id is not None and not completed_normally:
                self._cancel_thread_executions(thread_id)

    @staticmethod
    def _cancel_thread_executions(thread_id: str) -> None:
        """Cancel every queued/running execution-agent task for this thread.

        Fires when stream_execute unwinds without natural completion — i.e.,
        the client halted via useChat.stop() or the generator errored. The
        TaskRegistry handles unknown/done request_ids gracefully (returns
        False), so the status filter is purely for cleaner logging.
        """
        from ..execution_agent.task_registry import get_task_registry

        registry = get_task_registry()
        store = get_execution_event_store()
        try:
            runs = store.list_runs(thread_id=thread_id, limit=200)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "halt cascade: list_runs failed",
                extra={"thread_id": thread_id, "error": str(exc)},
            )
            return
        cancelled: list[str] = []
        for run in runs:
            if run["status"] in ("queued", "running"):
                if registry.cancel(run["requestId"]):
                    cancelled.append(run["requestId"])
        if cancelled:
            logger.info(
                "halt cascade: cancelled execution tasks",
                extra={"thread_id": thread_id, "request_ids": cancelled},
            )

    def _persist_assistant_message(
        self,
        thread_id: str,
        accumulator: _AssistantPartsAccumulator,
        *,
        turn_index: int | None = None,
    ) -> None:
        """Best-effort persistence of the assistant turn into threads.db.

        Runs in finally so it executes on normal end, exception, AND client
        disconnect. Failures here must not raise out of stream_execute —
        the stream already finished from the client's perspective.

        Passing `turn_index` co-locates this assistant message with the
        user message that triggered it, so concurrent turns can't
        interleave (a slow turn finishing after a fast one still sorts
        ahead of the fast turn's assistant message).
        """
        try:
            repository = get_thread_repository()
            content = accumulator.text_content()
            _ = repository.create_message(
                thread_id,
                role="assistant",
                content=content,
                parts=accumulator.parts,
                turn_index=turn_index,
            )
        except ThreadNotFoundError:
            logger.warning(
                "thread vanished before assistant message could persist",
                extra={"thread_id": thread_id},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "failed to persist assistant message",
                extra={"thread_id": thread_id, "error": str(exc)},
            )

    # Handle incoming messages from execution agents and generate appropriate responses
    async def handle_agent_message(self, agent_message: str) -> InteractionResult:
        """Process a status update emitted by an execution agent."""

        try:
            transcript_before = self._load_conversation_transcript()
            recent_transcript = self._load_recent_conversation_transcript()
            self.conversation_log.record_agent_message(agent_message)

            system_prompt = build_system_prompt()
            messages = _mutable_messages(
                prepare_message_with_history(
                    agent_message,
                    transcript_before,
                    recent_transcript=recent_transcript,
                    message_type="agent",
                )
            )

            logger.info("Processing execution agent results")
            summary = await self._run_interaction_loop(system_prompt, messages)

            final_response = self._finalize_response(summary)

            if final_response and not summary.user_messages:
                self.conversation_log.record_reply(final_response)

            return InteractionResult(
                success=True,
                response=final_response,
                execution_agents_used=len(summary.execution_agents),
            )

        except Exception as exc:
            logger.exception(f"Interaction agent (agent message) failed: {exc}")
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )

    # Core interaction loop that handles LLM calls and tool executions until completion
    async def _run_interaction_loop(
        self,
        system_prompt: str,
        messages: list[ChatMessagePayload],
    ) -> _LoopSummary:
        """Iteratively query the LLM until it issues a final response."""

        summary = _LoopSummary()
        # Per-tool budget for schema-validation retries. Independent of
        # MAX_TOOL_ITERATIONS so a single stuck tool can't monopolize the
        # whole run.
        validation_failures: dict[str, int] = {}

        for _ in range(self.MAX_TOOL_ITERATIONS):
            response = await self._make_llm_call(system_prompt, messages)
            assistant_message = self._extract_assistant_message(response)

            assistant_content = str(assistant_message.get("content") or "").strip()
            if assistant_content:
                summary.last_assistant_text = assistant_content

            raw_tool_calls = assistant_message.get("tool_calls") or []
            parsed_tool_calls = self._parse_tool_calls(raw_tool_calls)

            assistant_entry: ChatMessagePayload = {
                "role": "assistant",
                "content": assistant_message.get("content", "") or "",
            }
            if raw_tool_calls:
                assistant_entry["tool_calls"] = raw_tool_calls
            messages.append(assistant_entry)

            if not parsed_tool_calls:
                break

            should_finish_after_tools = False
            for tool_call in parsed_tool_calls:
                summary.tool_names.append(tool_call.name)

                if tool_call.name == "send_message_to_agent":
                    memory_id = tool_call.arguments.get("memory_id")
                    if isinstance(memory_id, str) and memory_id:
                        summary.execution_agents.add(memory_id)
                if tool_call.name == "send_messages_to_agents":
                    raw_items = tool_call.arguments.get("items")
                    items = raw_items if isinstance(raw_items, list) else []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        memory_id = item.get("memory_id")
                        if isinstance(memory_id, str) and memory_id:
                            summary.execution_agents.add(memory_id)

                invalid_args_message = self._check_tool_call_validation(
                    tool_call, validation_failures
                )
                if invalid_args_message is not None:
                    messages.append(invalid_args_message)
                    continue

                result = self._execute_tool(tool_call)

                if result.user_message:
                    summary.user_messages.append(result.user_message)
                elif self._is_execution_submission(cast(object, result.payload)):
                    summary.last_assistant_text = ""
                    should_finish_after_tools = True

                tool_message: ChatMessagePayload = {
                    "role": "tool",
                    "tool_call_id": tool_call.identifier or tool_call.name,
                    "content": self._format_tool_result(tool_call, result),
                }
                messages.append(tool_message)

            if should_finish_after_tools:
                break
        else:
            raise RuntimeError("Reached tool iteration limit without final response")

        if not summary.user_messages and not summary.last_assistant_text:
            logger.warning("Interaction loop exited without assistant content")

        return summary

    MAX_AGENT_PHASES: ClassVar[int] = 4
    EXECUTION_PHASE_TIMEOUT_SECONDS: ClassVar[float] = 300.0

    async def _run_streaming_interaction_loop(
        self,
        system_prompt: str,
        messages: list[ChatMessagePayload],
        execution_request_ids: set[str],
        execution_subscription: ExecutionEventSubscription,
        run_id: str,
        phase: int = 0,
    ) -> AsyncIterator[str]:
        summary = _LoopSummary()
        emitted_execution_event_ids: set[int] = set()
        execution_store = get_execution_event_store()
        # Per-tool validation-retry budget shared across iterations of this
        # streaming loop. Same rationale as the non-streaming loop.
        validation_failures: dict[str, int] = {}

        async def flush_live_execution_events() -> AsyncIterator[str]:
            while not execution_subscription.queue.empty():
                event = await execution_subscription.queue.get()
                event_id = self._execution_event_id(event)
                if event_id is not None:
                    emitted_execution_event_ids.add(event_id)
                yield ui_stream.sse_part(ui_stream.data_agent_event(event))
                yield ui_stream.sse_part(ui_stream.data_execution_event(event))

        async def emit_recorded_execution_events() -> AsyncIterator[str]:
            for request_id in sorted(execution_request_ids):
                run = execution_store.get_run(request_id)
                if run is None:
                    continue
                workspace_id = require_current_workspace()
                for event in execution_store.list_events(request_id):
                    payload: ExecutionEventPayload = {
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
                    event_id = self._execution_event_id(payload)
                    if event_id is not None and event_id in emitted_execution_event_ids:
                        continue
                    if event_id is not None:
                        emitted_execution_event_ids.add(event_id)
                    yield ui_stream.sse_part(ui_stream.data_agent_event(payload))
                    yield ui_stream.sse_part(ui_stream.data_execution_event(payload))

        for iteration in range(self.MAX_TOOL_ITERATIONS):
            yield ui_stream.sse_part(ui_stream.start_step())
            yield self._agent_event_chunk(
                run_id=run_id, event_type="model.started", state="running"
            )
            assistant_message: dict[str, object] = {
                "role": "assistant",
                "content": "",
            }
            tool_calls_by_index: dict[int, _StreamingToolCall] = {}
            text_part_id = f"text-{iteration}-{uuid.uuid4()}"
            text_started = False
            reasoning_part_id = f"reasoning-{iteration}-{uuid.uuid4()}"
            reasoning_started = False

            async for response in self._stream_llm_call(system_prompt, messages):
                async for event_chunk in flush_live_execution_events():
                    yield event_chunk

                if not response["choices"]:
                    continue
                delta = response["choices"][0]["delta"]
                content_delta = delta.get("content")
                if isinstance(content_delta, str) and content_delta:
                    if not text_started:
                        text_started = True
                        yield ui_stream.sse_part(ui_stream.text_start(text_part_id))
                    assistant_message["content"] = (
                        str(assistant_message["content"]) + content_delta
                    )
                    yield ui_stream.sse_part(
                        ui_stream.text_delta(text_part_id, content_delta)
                    )
                    yield self._agent_event_chunk(
                        run_id=run_id,
                        event_type="model.text.delta",
                        state="running",
                        text=content_delta,
                    )

                reasoning_delta = delta.get("reasoning")
                if isinstance(reasoning_delta, str) and reasoning_delta:
                    if not reasoning_started:
                        reasoning_started = True
                        yield ui_stream.sse_part(
                            ui_stream.reasoning_start(reasoning_part_id)
                        )
                    yield ui_stream.sse_part(
                        ui_stream.reasoning_delta(reasoning_part_id, reasoning_delta)
                    )
                    yield self._agent_event_chunk(
                        run_id=run_id,
                        event_type="model.reasoning.delta",
                        state="running",
                        text=reasoning_delta,
                    )

                for raw_tool_delta in delta.get("tool_calls") or []:
                    index = int(raw_tool_delta.get("index") or 0)
                    existing = tool_calls_by_index.setdefault(
                        index,
                        _StreamingToolCall(
                            identifier=raw_tool_delta.get("id")
                            or f"tool-{iteration}-{index}"
                        ),
                    )
                    delta_identifier = raw_tool_delta.get("id")
                    if delta_identifier:
                        existing.identifier = delta_identifier
                    function_delta = raw_tool_delta.get("function") or {}
                    if function_delta.get("name"):
                        existing.name = function_delta["name"]
                    argument_delta = function_delta.get("arguments")
                    if isinstance(argument_delta, str) and argument_delta:
                        if not existing.input_started:
                            existing.input_started = True
                            yield self._agent_event_chunk(
                                run_id=run_id,
                                event_type="tool.input.started",
                                state="running",
                                tool_call_id=existing.identifier,
                                tool_name=existing.name or "tool",
                            )
                            yield ui_stream.sse_part(
                                ui_stream.tool_input_start(
                                    existing.identifier,
                                    existing.name or "tool",
                                )
                            )
                        existing.arguments += argument_delta
                        yield self._agent_event_chunk(
                            run_id=run_id,
                            event_type="tool.input.delta",
                            state="running",
                            tool_call_id=existing.identifier,
                            tool_name=existing.name or "tool",
                            text=argument_delta,
                        )
                        yield ui_stream.sse_part(
                            ui_stream.tool_input_delta(
                                existing.identifier, argument_delta
                            )
                        )

            if text_started:
                yield ui_stream.sse_part(ui_stream.text_end(text_part_id))
            if reasoning_started:
                yield ui_stream.sse_part(ui_stream.reasoning_end(reasoning_part_id))
            yield self._agent_event_chunk(
                run_id=run_id, event_type="model.completed", state="completed"
            )
            assistant_content = str(assistant_message.get("content") or "").strip()
            if assistant_content:
                summary.last_assistant_text = assistant_content

            raw_tool_calls = [
                raw.as_openrouter() for _, raw in sorted(tool_calls_by_index.items())
            ]
            parsed_tool_calls = self._parse_tool_calls(raw_tool_calls)

            assistant_entry: ChatMessagePayload = {
                "role": "assistant",
                "content": assistant_message.get("content", "") or "",
            }
            if raw_tool_calls:
                assistant_entry["tool_calls"] = raw_tool_calls
            messages.append(assistant_entry)

            if not parsed_tool_calls:
                if assistant_content and not text_started:
                    yield ui_stream.sse_part(ui_stream.text_start(text_part_id))
                    yield ui_stream.sse_part(
                        ui_stream.text_delta(text_part_id, assistant_content)
                    )
                    yield ui_stream.sse_part(ui_stream.text_end(text_part_id))
                yield ui_stream.sse_part(ui_stream.finish_step())
                break

            should_finish_after_tools = False
            for tool_call in parsed_tool_calls:
                yield ui_stream.sse_part(
                    ui_stream.tool_input_available(
                        tool_call.identifier or tool_call.name,
                        tool_call.name,
                        tool_call.arguments,
                    )
                )
                yield self._agent_event_chunk(
                    run_id=run_id,
                    event_type="tool.input.available",
                    state="input-available",
                    tool_call_id=tool_call.identifier or tool_call.name,
                    tool_name=tool_call.name,
                    input_data=tool_call.arguments,
                )
                streaming_tc = next(
                    (
                        tc
                        for tc in tool_calls_by_index.values()
                        if tc.identifier == (tool_call.identifier or tool_call.name)
                    ),
                    None,
                )
                summary.tool_names.append(tool_call.name)
                invalid_args_message = self._check_tool_call_validation(
                    tool_call, validation_failures
                )
                if invalid_args_message is not None:
                    yield self._agent_event_chunk(
                        run_id=run_id,
                        event_type="tool.output.error",
                        state="output-error",
                        tool_call_id=tool_call.identifier or tool_call.name,
                        tool_name=tool_call.name,
                        output=None,
                        error=str(invalid_args_message["content"]),
                    )
                    messages.append(invalid_args_message)
                    continue
                result = self._execute_tool(tool_call)
                result_payload = self._json_value(cast(object, result.payload))
                self._collect_execution_request_ids(
                    result_payload, execution_request_ids
                )
                async for submitted_chunk in self._execution_submitted_chunks(
                    run_id, result_payload
                ):
                    yield submitted_chunk
                if result.success:
                    async for event_chunk in emit_recorded_execution_events():
                        yield event_chunk
                yield self._agent_event_chunk(
                    run_id=run_id,
                    event_type=(
                        "tool.output.available"
                        if result.success
                        else "tool.output.error"
                    ),
                    state="output-available" if result.success else "output-error",
                    tool_call_id=tool_call.identifier or tool_call.name,
                    tool_name=tool_call.name,
                    output=result_payload if result.success else None,
                    error=None if result.success else str(result_payload),
                )
                yield ui_stream.sse_part(
                    ui_stream.tool_output_available(
                        tool_call.identifier or tool_call.name,
                        result_payload,
                    )
                )
                async for event_chunk in flush_live_execution_events():
                    yield event_chunk

                if result.user_message:
                    summary.user_messages.append(result.user_message)
                    already_streamed = (
                        text_started
                        and result.user_message.strip() == assistant_content
                    )
                    msg_streamed_via_tool = (
                        streaming_tc is not None
                        and streaming_tc.msg_text_part_id is not None
                    )
                    if not already_streamed and not msg_streamed_via_tool:
                        reply_part_id = f"text-tool-{uuid.uuid4()}"
                        yield ui_stream.sse_part(ui_stream.text_start(reply_part_id))
                        yield ui_stream.sse_part(
                            ui_stream.text_delta(reply_part_id, result.user_message)
                        )
                        yield ui_stream.sse_part(ui_stream.text_end(reply_part_id))
                elif self._is_execution_submission(cast(object, result.payload)):
                    summary.last_assistant_text = ""
                    should_finish_after_tools = True

                tool_message: ChatMessagePayload = {
                    "role": "tool",
                    "tool_call_id": tool_call.identifier or tool_call.name,
                    "content": self._format_tool_result(tool_call, result),
                }
                messages.append(tool_message)

            yield ui_stream.sse_part(ui_stream.finish_step())
            if should_finish_after_tools:
                break
        else:
            raise RuntimeError("Reached tool iteration limit without final response")

        next_messages: list[ChatMessagePayload] | None = None
        if phase + 1 < self.MAX_AGENT_PHASES and execution_request_ids:
            pending: set[str] = set()
            phase_results: dict[str, str] = {}
            for request_id in execution_request_ids:
                result = self._read_execution_result(request_id)
                if result is not None:
                    phase_results[request_id] = result
                else:
                    pending.add(request_id)

            while pending:
                try:
                    event = await asyncio.wait_for(
                        execution_subscription.queue.get(),
                        timeout=self.EXECUTION_PHASE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Timed out waiting for execution results",
                        extra={"pending": sorted(pending)},
                    )
                    break

                eid = self._execution_event_id(event)
                if eid is None or eid not in emitted_execution_event_ids:
                    if eid is not None:
                        emitted_execution_event_ids.add(eid)
                    yield ui_stream.sse_part(ui_stream.data_agent_event(event))
                    yield ui_stream.sse_part(ui_stream.data_execution_event(event))

                req_id = str(event.get("requestId") or "")
                ev = event.get("event") or {}
                ev_type = str(ev.get("type") or "")
                if req_id in pending:
                    if ev_type == "run.completed":
                        phase_results[req_id] = str(ev.get("text") or "")
                        pending.discard(req_id)
                    elif ev_type == "run.failed":
                        err = str(ev.get("error") or "unknown error")
                        phase_results[req_id] = f"[execution failed: {err}]"
                        pending.discard(req_id)

            agent_message_text = self._format_agent_results(phase_results)
            if agent_message_text:
                self.conversation_log.record_agent_message(agent_message_text)
                next_messages = _mutable_messages(
                    prepare_message_with_history(
                        agent_message_text,
                        self._load_conversation_transcript(),
                        recent_transcript=self._load_recent_conversation_transcript(),
                        message_type="agent",
                    )
                )

        if next_messages is not None:
            async for chunk in self._run_streaming_interaction_loop(
                system_prompt,
                next_messages,
                execution_request_ids,
                execution_subscription,
                run_id,
                phase=phase + 1,
            ):
                yield chunk
            return

        final_response = self._finalize_response(summary)
        if final_response and not summary.user_messages:
            self.conversation_log.record_reply(final_response)
        yield self._agent_event_chunk(
            run_id=run_id,
            event_type="run.completed",
            state="completed",
            text=final_response,
        )

    def _read_execution_result(self, request_id: str) -> str | None:
        store = get_execution_event_store()
        try:
            events = list(store.list_events(request_id))
        except Exception:
            return None
        for event in reversed(events):
            etype = str(event.get("type") or "")
            if etype == "run.completed":
                return str(event.get("text") or "")
            if etype == "run.failed":
                err = str(event.get("error") or "unknown error")
                return f"[execution failed: {err}]"
        return None

    def _format_agent_results(self, results: Mapping[str, str]) -> str:
        chunks: list[str] = []
        for request_id, text in results.items():
            body = text.strip()
            if not body:
                continue
            chunks.append(
                f'<agent_message request_id="{request_id}">{body}</agent_message>'
            )
        return "\n\n".join(chunks)

    def _agent_event_chunk(
        self,
        *,
        run_id: str,
        event_type: str,
        state: str | None = None,
        thread_id: str | None = None,
        parent_run_id: str | None = None,
        scope: str = "interaction",
        title: str = "Interaction",
        memory_id: str | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        text: str | None = None,
        input_data: JsonValue = None,
        output: JsonValue = None,
        error: str | None = None,
    ) -> str:
        payload = {
            "runId": run_id,
            "requestId": run_id,
            "threadId": thread_id,
            "parentRunId": parent_run_id,
            "scope": scope,
            "title": title,
            "memoryId": memory_id,
            "event": {
                "id": None,
                "runId": run_id,
                "sequence": 0,
                "type": event_type,
                "state": state,
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "text": text,
                "input": input_data,
                "output": output,
                "error": error,
                "createdAt": str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z")),
            },
        }
        return ui_stream.sse_part(ui_stream.data_agent_event(payload))

    def _collect_execution_request_ids(
        self, payload: JsonValue, request_ids: set[str]
    ) -> None:
        if not isinstance(payload, dict):
            return
        request_id = payload.get("request_id")
        if isinstance(request_id, str) and request_id:
            request_ids.add(request_id)
        raw_children = payload.get("children")
        children = raw_children if isinstance(raw_children, list) else []
        for child in children:
            if not isinstance(child, dict):
                continue
            child_request_id = child.get("request_id")
            if isinstance(child_request_id, str):
                request_ids.add(child_request_id)

    async def _execution_submitted_chunks(
        self, parent_run_id: str, payload: JsonValue
    ) -> AsyncIterator[str]:
        if not isinstance(payload, dict):
            return
        items: list[dict[str, JsonValue]] = []
        if isinstance(payload.get("request_id"), str):
            items.append(payload)
        raw_children = payload.get("children")
        if isinstance(raw_children, list):
            items.extend(child for child in raw_children if isinstance(child, dict))
        for item in items:
            status = item.get("status")
            request_id = item.get("request_id")
            if status not in {"submitted", "already_in_progress"}:
                continue
            if not isinstance(request_id, str) or not request_id:
                continue
            memory_id = item.get("memory_id")
            title = item.get("title") or memory_id or "Execution"
            yield self._agent_event_chunk(
                run_id=request_id,
                event_type="execution.submitted",
                state="queued",
                parent_run_id=parent_run_id,
                scope="execution",
                title=str(title),
                memory_id=str(memory_id or ""),
                text=str(item.get("message") or ""),
                output=item,
            )

    def _execution_event_id(self, payload: ExecutionEventPayload) -> int | None:
        event = payload["event"]
        event_id = event.get("id")
        if isinstance(event_id, int):
            return event_id
        return None

    def _is_execution_submission(self, payload: object) -> bool:
        if not isinstance(payload, Mapping):
            return False
        payload_data = cast(Mapping[str, object], payload)
        if payload_data.get("status") not in {"submitted", "already_in_progress"}:
            return False
        if isinstance(payload_data.get("request_id"), str):
            return True
        raw_children = payload_data.get("children")
        children = (
            cast(list[object], raw_children) if isinstance(raw_children, list) else []
        )
        for child in children:
            if not isinstance(child, Mapping):
                continue
            child_data = cast(Mapping[str, object], child)
            if child_data.get("status") in {
                "submitted",
                "already_in_progress",
            } and isinstance(child_data.get("request_id"), str):
                return True
        return False

    # Load conversation history, preferring summarized version if available
    def _load_conversation_transcript(self) -> str:
        if self.settings.summarization_enabled:
            rendered = self.working_memory_log.render_transcript()
            if rendered.strip():
                return rendered
        return self.conversation_log.load_transcript()

    def _load_recent_conversation_transcript(self) -> str:
        return self.conversation_log.load_recent_transcript(
            self.settings.conversation_recent_entries_limit
        )

    # Execute API call to OpenRouter with system prompt, messages, and tool schemas
    async def _make_llm_call(
        self,
        system_prompt: str,
        messages: list[ChatMessagePayload],
    ) -> OpenRouterChatCompletion:
        """Make an LLM call via OpenRouter."""

        logger.debug(
            "Interaction agent calling LLM",
            extra={"model": self.model, "tools": len(self.tool_schemas)},
        )
        self._log_prompt_payload(system_prompt, messages)
        return await request_chat_completion(
            model=self.model,
            messages=self._message_text_payloads(messages),
            system=system_prompt,
            api_key=self.api_key,
            tools=self.tool_schemas,
        )

    async def _stream_llm_call(
        self,
        system_prompt: str,
        messages: list[ChatMessagePayload],
    ) -> AsyncIterator[OpenRouterChatCompletionChunk]:
        logger.debug(
            "Interaction agent streaming LLM",
            extra={"model": self.model, "tools": len(self.tool_schemas)},
        )
        self._log_prompt_payload(system_prompt, messages)
        async for chunk in stream_chat_completion(
            model=self.model,
            messages=self._message_text_payloads(messages),
            system=system_prompt,
            api_key=self.api_key,
            tools=self.tool_schemas,
        ):
            yield chunk

    def _message_text_payloads(
        self, messages: Sequence[Mapping[str, object]]
    ) -> list[Mapping[str, object]]:
        payloads: list[Mapping[str, object]] = []
        for message in messages:
            payload: dict[str, object] = {
                "role": str(message.get("role") or ""),
                "content": str(message.get("content") or ""),
            }
            if "tool_calls" in message:
                payload["tool_calls"] = message.get("tool_calls")
            if "tool_call_id" in message:
                tool_call_id = message.get("tool_call_id")
                payload["tool_call_id"] = (
                    str(tool_call_id) if tool_call_id is not None else None
                )
            payloads.append(payload)
        return payloads

    def _log_prompt_payload(
        self,
        system_prompt: str,
        messages: list[ChatMessagePayload],
    ) -> None:
        """Log prompt shape by default, with content only in debug-content mode."""
        include_content = self.settings.memory_debug_log_content
        extra: dict[str, object] = {
            "model": self.model,
            "tools": len(self.tool_schemas),
            "system_prompt_chars": len(system_prompt),
            "message_count": len(messages),
            "message_chars": sum(
                len(str(message.get("content") or "")) for message in messages
            ),
            "message_roles": [str(message.get("role") or "") for message in messages],
            "debug_content": include_content,
        }
        if include_content:
            extra["system_prompt"] = system_prompt
            extra["messages"] = [
                {
                    "role": message.get("role"),
                    "content": message.get("content"),
                    "tool_call_id": message.get("tool_call_id"),
                }
                for message in messages
            ]
            logger.info(
                (
                    "Interaction agent prompt prepared\n"
                    f"<system_prompt>\n{system_prompt}\n</system_prompt>\n"
                    f"<messages>\n{json.dumps(extra['messages'], ensure_ascii=False, default=str)}\n</messages>"
                ),
                extra=extra,
            )
            return
        logger.info(
            (
                "Interaction agent prompt prepared; set MEMORY_DEBUG_LOG_CONTENT=1 "
                "to log <relevant_memories> and <recent_events> prompt content\n"
            )
            + f'<prompt_shape model="{self.model}" tools="{len(self.tool_schemas)}" '
            + f'system_prompt_chars="{len(system_prompt)}" messages="{len(messages)}" '
            + f'message_chars="{extra["message_chars"]}" />',
            extra=extra,
        )

    # Extract the assistant's message from the OpenRouter API response structure
    def _extract_assistant_message(
        self, response: OpenRouterChatCompletion
    ) -> OpenRouterAssistantMessage:
        """Return the assistant message from the raw response payload."""

        if not response["choices"]:
            raise RuntimeError("LLM response did not include an assistant message")
        return response["choices"][0]["message"]

    # Convert raw LLM tool calls into structured _ToolCall objects with validation
    def _parse_tool_calls(
        self, raw_tool_calls: Sequence[OpenRouterToolCall]
    ) -> list[_ToolCall]:
        """Normalize tool call payloads from the LLM."""

        parsed: list[_ToolCall] = []
        for raw in raw_tool_calls:
            function_block = raw["function"]
            name = function_block["name"]
            if not name:
                logger.warning("Skipping tool call without name", extra={"tool": raw})
                continue

            arguments, error = self._parse_tool_arguments(function_block["arguments"])
            if error:
                logger.warning(
                    "Tool call arguments invalid", extra={"tool": name, "error": error}
                )
                parsed.append(
                    _ToolCall(
                        identifier=raw["id"],
                        name=name,
                        arguments={"__invalid_arguments__": error},
                    )
                )
                continue

            parsed.append(
                _ToolCall(identifier=raw["id"], name=name, arguments=arguments)
            )

        return parsed

    # Parse and validate tool arguments from various formats (dict, JSON string, etc.)
    def _parse_tool_arguments(
        self, raw_arguments: object
    ) -> tuple[ToolArguments, str | None]:
        """Convert tool arguments into a dictionary, reporting errors."""

        if raw_arguments is None:
            return {}, None

        if isinstance(raw_arguments, dict):
            return self._json_object(cast(Mapping[object, object], raw_arguments)), None

        if isinstance(raw_arguments, str):
            if not raw_arguments.strip():
                return {}, None
            try:
                parsed = cast(object, json.loads(raw_arguments))
            except json.JSONDecodeError as exc:
                return {}, f"invalid json: {exc}"
            if isinstance(parsed, dict):
                return self._json_object(cast(Mapping[object, object], parsed)), None
            return {}, "decoded arguments were not an object"

        return {}, f"unsupported argument type: {type(raw_arguments).__name__}"

    def _json_value(self, value: object) -> JsonValue:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Mapping):
            return self._json_object(cast(Mapping[object, object], value))
        if isinstance(value, Sequence) and not isinstance(
            value, str | bytes | bytearray
        ):
            return [self._json_value(item) for item in value]
        return str(value)

    def _json_object(self, payload: Mapping[object, object]) -> JsonObject:
        return {str(key): self._json_value(value) for key, value in payload.items()}

    # Validate tool args against the catalog JSON schema (if any). Returns
    # a tool-error message to append in place of dispatch when validation
    # fails, or None when args are acceptable. Mutates validation_failures
    # so callers can enforce the per-tool retry budget across iterations.
    def _check_tool_call_validation(
        self,
        tool_call: _ToolCall,
        validation_failures: dict[str, int],
    ) -> ChatMessagePayload | None:
        schema_errors = validate_tool_args(
            tool_call.name, cast(dict[str, object], tool_call.arguments)
        )
        if not schema_errors:
            return None
        validation_failures[tool_call.name] = (
            validation_failures.get(tool_call.name, 0) + 1
        )
        attempts = validation_failures[tool_call.name]
        exhausted = attempts > MAX_VALIDATION_RETRIES_PER_TOOL
        failure_payload: dict[str, object] = {
            "error": "invalid_arguments",
            "tool_name": tool_call.name,
            "details": schema_errors,
            "attempt": attempts,
        }
        if exhausted:
            failure_payload["reason"] = "max_validation_retries"
            failure_payload["instruction"] = (
                f"Do not call {tool_call.name} again this run. "
                "Tell the user the call could not be constructed."
            )
        logger.warning(
            "Tool args failed schema validation",
            extra={
                "tool": tool_call.name,
                "attempt": attempts,
                "errors": schema_errors,
            },
        )
        return {
            "role": "tool",
            "tool_call_id": tool_call.identifier or tool_call.name,
            "content": json.dumps(failure_payload),
        }

    # Execute tool calls with error handling and logging, returning standardized results
    def _execute_tool(self, tool_call: _ToolCall) -> ToolResult:
        """Execute a tool call and convert low-level errors into structured results."""

        if "__invalid_arguments__" in tool_call.arguments:
            error = tool_call.arguments["__invalid_arguments__"]
            self._log_tool_invocation(
                tool_call, stage="rejected", detail={"error": error}
            )
            return ToolResult(success=False, payload={"error": error})

        try:
            self._log_tool_invocation(tool_call, stage="start")
            result = handle_tool_call(tool_call.name, tool_call.arguments)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Tool execution crashed",
                extra={"tool": tool_call.name, "error": str(exc)},
            )
            self._log_tool_invocation(
                tool_call,
                stage="error",
                detail={"error": str(exc)},
            )
            return ToolResult(success=False, payload={"error": str(exc)})

        status = "success" if result.success else "error"
        logger.debug(
            "Tool executed",
            extra={
                "tool": tool_call.name,
                "status": status,
            },
        )
        self._log_tool_invocation(tool_call, stage="done", result=result)
        return result

    # Format tool execution results into JSON for LLM consumption
    def _format_tool_result(self, tool_call: _ToolCall, result: ToolResult) -> str:
        """Render a tool execution result back to the LLM."""

        payload: JsonObject = {
            "tool": tool_call.name,
            "status": "success" if result.success else "error",
            "arguments": {
                key: value
                for key, value in tool_call.arguments.items()
                if key != "__invalid_arguments__"
            },
        }

        if result.payload is not None:
            key = "result" if result.success else "error"
            shrunk = (
                shrink_gmail_tool_result(tool_call.name, result.payload)
                if result.success
                else result.payload
            )
            payload[key] = self._json_value(shrunk)

        return self._safe_json_dump(payload)

    # Safely serialize objects to JSON with fallback to string representation
    def _safe_json_dump(self, payload: object) -> str:
        """Serialize payload to JSON, falling back to repr on failure."""

        try:
            return json.dumps(payload, default=str)
        except TypeError:
            return repr(payload)

    # Log tool execution stages (start, done, error) with structured metadata
    def _log_tool_invocation(
        self,
        tool_call: _ToolCall,
        *,
        stage: str,
        result: ToolResult | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        """Emit structured logs for tool lifecycle events."""

        cleaned_args = {
            key: value
            for key, value in tool_call.arguments.items()
            if key != "__invalid_arguments__"
        }

        log_payload: dict[str, object] = {
            "tool": tool_call.name,
            "stage": stage,
            "arguments": cleaned_args,
        }

        if result is not None:
            log_payload["success"] = result.success
            if result.payload is not None:
                log_payload["payload"] = self._json_value(result.payload)

        if detail:
            log_payload.update(detail)

        if stage == "done":
            logger.info(f"Tool '{tool_call.name}' completed")
        elif stage in {"error", "rejected"}:
            logger.warning(f"Tool '{tool_call.name}' {stage}")
        else:
            logger.debug(f"Tool '{tool_call.name}' {stage}")

    # Determine final user-facing response from interaction loop summary
    def _finalize_response(self, summary: _LoopSummary) -> str:
        """Decide what text should be exposed to the user as the final reply."""

        if summary.user_messages:
            return summary.user_messages[-1]

        return summary.last_assistant_text
