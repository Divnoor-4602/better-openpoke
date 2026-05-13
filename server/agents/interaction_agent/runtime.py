"""Interaction Agent Runtime - handles LLM calls for user and agent turns."""

import json
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, cast

from ...config import Settings, get_settings
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
from ...services.execution import (
    ExecutionEventPayload,
    ExecutionEventSubscription,
    get_execution_event_store,
)
from .agent import build_system_prompt, prepare_message_with_history
from .tools import ToolResult, get_tool_schemas, handle_tool_call

ChatMessagePayload = dict[str, object]
ToolArguments = dict[str, JsonValue]


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

    def as_openrouter(self) -> OpenRouterToolCall:
        return {
            "id": self.identifier,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


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

    async def stream_execute(self, user_message: str) -> AsyncIterator[str]:
        """Handle a user message and emit AI SDK UI Message Stream SSE parts."""

        execution_store = get_execution_event_store()
        subscription: ExecutionEventSubscription | None = None
        try:
            subscription = execution_store.subscribe(set())
            message_id = f"msg-{uuid.uuid4()}"
            yield ui_stream.sse_part(ui_stream.start_message(message_id))
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

            async for chunk in self._run_streaming_interaction_loop(
                system_prompt,
                messages,
                subscription.request_ids,
                subscription,
            ):
                yield chunk
        except Exception as exc:
            logger.exception(f"Streaming interaction agent failed: {exc}")
            yield ui_stream.sse_part(ui_stream.error_part(str(exc)))
        else:
            yield ui_stream.sse_part(ui_stream.finish_message())
            yield ui_stream.DONE
        finally:
            if subscription is not None:
                get_execution_event_store().unsubscribe(subscription)

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

                result = self._execute_tool(tool_call)

                if result.user_message:
                    summary.user_messages.append(result.user_message)
                    should_finish_after_tools = True
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

    async def _run_streaming_interaction_loop(
        self,
        system_prompt: str,
        messages: list[ChatMessagePayload],
        execution_request_ids: set[str],
        execution_subscription: ExecutionEventSubscription,
    ) -> AsyncIterator[str]:
        summary = _LoopSummary()
        emitted_execution_event_ids: set[int] = set()
        execution_store = get_execution_event_store()

        async def flush_live_execution_events() -> AsyncIterator[str]:
            while not execution_subscription.queue.empty():
                event = await execution_subscription.queue.get()
                event_id = self._execution_event_id(event)
                if event_id is not None:
                    emitted_execution_event_ids.add(event_id)
                yield ui_stream.sse_part(ui_stream.data_execution_event(event))

        async def emit_recorded_execution_events() -> AsyncIterator[str]:
            for request_id in sorted(execution_request_ids):
                run = execution_store.get_run(request_id)
                if run is None:
                    continue
                for event in execution_store.list_events(request_id):
                    payload: ExecutionEventPayload = {
                        "requestId": run["requestId"],
                        "memoryId": run["memoryId"],
                        "parentMemoryId": run["parentMemoryId"],
                        "title": run["title"],
                        "event": event,
                    }
                    event_id = self._execution_event_id(payload)
                    if event_id is not None and event_id in emitted_execution_event_ids:
                        continue
                    if event_id is not None:
                        emitted_execution_event_ids.add(event_id)
                    yield ui_stream.sse_part(ui_stream.data_execution_event(payload))

        for iteration in range(self.MAX_TOOL_ITERATIONS):
            yield ui_stream.sse_part(ui_stream.start_step())
            assistant_message: dict[str, object] = {
                "role": "assistant",
                "content": "",
            }
            tool_calls_by_index: dict[int, _StreamingToolCall] = {}
            text_part_id = f"text-{iteration}-{uuid.uuid4()}"

            async for response in self._stream_llm_call(system_prompt, messages):
                async for event_chunk in flush_live_execution_events():
                    yield event_chunk

                if not response["choices"]:
                    continue
                delta = response["choices"][0]["delta"]
                content_delta = delta.get("content")
                if isinstance(content_delta, str) and content_delta:
                    assistant_message["content"] = (
                        str(assistant_message["content"]) + content_delta
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
                            yield ui_stream.sse_part(
                                ui_stream.tool_input_start(
                                    existing.identifier,
                                    existing.name or "tool",
                                )
                            )
                        existing.arguments += argument_delta
                        yield ui_stream.sse_part(
                            ui_stream.tool_input_delta(
                                existing.identifier, argument_delta
                            )
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
                if assistant_content:
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
                summary.tool_names.append(tool_call.name)
                result = self._execute_tool(tool_call)
                result_payload = self._json_value(cast(object, result.payload))
                self._collect_execution_request_ids(
                    result_payload, execution_request_ids
                )
                if result.success:
                    async for event_chunk in emit_recorded_execution_events():
                        yield event_chunk
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
                    should_finish_after_tools = True
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

        final_response = self._finalize_response(summary)
        if final_response and not summary.user_messages:
            self.conversation_log.record_reply(final_response)

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
            payload[key] = self._json_value(result.payload)

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
