"""Simplified Execution Agent Runtime."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from ...config import get_settings
from ...logging_config import logger
from ...openrouter_client import (
    JsonValue,
    OpenRouterAssistantMessage,
    OpenRouterChatCompletion,
    request_chat_completion,
)
from ...services.execution import get_execution_event_store
from ...services.gmail.llm_payload import shrink_gmail_tool_result
from ...services.memory import get_memory_store
from ...services.memory.store import MemoryStore
from ..tool_schemas import MAX_VALIDATION_RETRIES_PER_TOOL, validate_tool_args
from .agent import ExecutionAgent
from .tools import get_tool_registry, get_tool_schemas


def _xml_attr(value: str) -> str:
    """Minimal escaping for XML attribute values (quotes + ampersand)."""
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


@dataclass
class ExecutionResult:
    """Result from an execution agent."""

    memory_id: str
    memory_title: str
    agent_name: str
    success: bool
    response: str
    error: str | None = None
    tools_executed: list[str] | None = None
    request_id: str | None = None


class ExecutionAgentRuntime:
    """Manages the execution of a single agent request."""

    MAX_TOOL_ITERATIONS: ClassVar[int] = 8

    memory_id: str
    memory_title: str
    run_id: str
    memory_store: MemoryStore
    agent: ExecutionAgent
    api_key: str | None
    model: str
    tool_registry: dict[str, Callable[..., object]]
    tool_schemas: list[dict[str, object]]

    # Initialize execution agent runtime with settings, tools, and agent instance
    def __init__(
        self,
        agent_name: str,
        memory_title: str | None = None,
        run_id: str | None = None,
    ):
        settings = get_settings()
        self.memory_id = agent_name
        self.memory_title = memory_title or agent_name
        self.run_id = run_id or str(uuid.uuid4())
        self.memory_store = get_memory_store()
        memory_context = self.memory_store.render_memory_context(self.memory_id)
        self._log_execution_memory_context(memory_context)
        self.agent = ExecutionAgent(
            agent_name,
            display_name=self.memory_title,
            memory_context=memory_context,
        )
        self.api_key = settings.openrouter_api_key
        self.model = settings.execution_agent_model
        self.tool_registry = get_tool_registry(agent_name=agent_name)
        self.tool_schemas = get_tool_schemas()

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
            )

    def _log_execution_memory_context(self, memory_context: str) -> None:
        include_content = get_settings().memory_debug_log_content
        memory = self.memory_store.get_memory(self.memory_id)
        lines = [
            "Execution agent memory context prepared",
            f'memory_id="{self.memory_id}" title="{self.memory_title}" context_chars="{len(memory_context)}" debug_content="{include_content}"',
        ]
        if memory is not None:
            lines.append(
                f'loaded_memory kind="{memory.kind}" links="{len(memory.links)}" recent_events="{len(memory.recent_events)}" updated_at="{memory.updated_at}"'
            )
            if memory.links:
                lines.append(
                    "links="
                    + repr(
                        [
                            f"{link.kind}:{self._truncate_log_value(link.value, 80)}"
                            for link in memory.links[:20]
                        ]
                    )
                )
            lines.append("<execution_memory_events>")
            for event in memory.recent_events[-12:]:
                line = (
                    f'event_id="{event.event_id}" type="{event.type}" '
                    f'timestamp="{event.timestamp or event.recorded_at}"'
                )
                if include_content:
                    line += f" text={self._truncate_log_value(event.text, 240)!r}"
                lines.append(line)
            lines.append("</execution_memory_events>")
        else:
            lines.append("loaded_memory=false")
        if include_content:
            lines.extend(
                [
                    "<execution_memory_context>",
                    memory_context,
                    "</execution_memory_context>",
                ]
            )
        logger.info("\n".join(lines))

    def _truncate_log_value(self, value: str, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    # Main execution loop for running agent with LLM calls and tool execution
    async def execute(self, instructions: str) -> ExecutionResult:
        """Execute the agent with given instructions."""
        try:
            # Build system prompt with history
            system_prompt = self.agent.build_system_prompt_with_history()

            # Start conversation with the instruction
            messages: list[Mapping[str, object]] = [
                {"role": "user", "content": instructions}
            ]
            tools_executed: list[str] = []
            created_drafts: list[dict[str, object]] = []
            final_response: str | None = None
            # Per-tool budget for schema-validation retries. Independent of
            # MAX_TOOL_ITERATIONS so a single stuck tool can't monopolize the
            # whole run. Keyed by tool name, not call id, since each retry
            # gets a fresh id from the LLM.
            validation_failures: dict[str, int] = {}

            for iteration in range(self.MAX_TOOL_ITERATIONS):
                # Drain any user follow-ups queued via send_followup_to_agent.
                # Treat them as authoritative amendments to the task — the
                # next LLM call sees them as <user_followup> turns.
                from .task_registry import get_task_registry

                followups = get_task_registry().drain_inbox(self.run_id)
                for followup in followups:
                    messages = [
                        *messages,
                        {
                            "role": "user",
                            "content": f"<user_followup>{followup}</user_followup>",
                        },
                    ]
                    get_execution_event_store().record_event(
                        request_id=self.run_id,
                        memory_id=self.memory_id,
                        event_type="status",
                        state="running",
                        text=f"received user follow-up: {followup}",
                    )

                logger.info(
                    f"[{self.agent.name}] Requesting plan (iteration {iteration + 1})"
                )
                get_execution_event_store().record_event(
                    request_id=self.run_id,
                    memory_id=self.memory_id,
                    event_type="model.started",
                    state="running",
                    text=f"Execution model request {iteration + 1}",
                )
                response = await self._make_llm_call(
                    system_prompt, messages, with_tools=True
                )
                get_execution_event_store().record_event(
                    request_id=self.run_id,
                    memory_id=self.memory_id,
                    event_type="model.completed",
                    state="completed",
                    text=f"Execution model response {iteration + 1}",
                )
                choices = response["choices"]
                if not choices:
                    raise RuntimeError(
                        "LLM response did not include an assistant message"
                    )
                assistant_message: OpenRouterAssistantMessage = choices[0]["message"]

                raw_tool_calls = list(assistant_message.get("tool_calls") or [])
                parsed_tool_calls = self._extract_tool_calls(raw_tool_calls)

                assistant_entry: dict[str, object] = {
                    "role": "assistant",
                    "content": assistant_message.get("content") or "",
                }
                if raw_tool_calls:
                    assistant_entry["tool_calls"] = raw_tool_calls
                messages = [*messages, assistant_entry]

                if not parsed_tool_calls:
                    final_response = str(
                        assistant_entry["content"] or "No action required."
                    )
                    break

                for tool_call in parsed_tool_calls:
                    tool_name = str(tool_call.get("name") or "")
                    _raw_args: object = tool_call.get("arguments")
                    tool_args: dict[str, object] = (
                        cast(dict[str, object], _raw_args)
                        if isinstance(_raw_args, dict)
                        else {}
                    )
                    call_id = tool_call.get("id")

                    if not tool_name:
                        logger.warning("Tool call missing name: %s", tool_call)
                        failure = {
                            "error": "Tool call missing name; unable to execute."
                        }
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": call_id or "unknown_tool",
                            "content": self._format_tool_result(
                                tool_name or "<unknown>", False, failure, tool_args
                            ),
                        }
                        messages = [*messages, tool_message]
                        continue

                    resolved_call_id = (
                        str(call_id)
                        if call_id is not None
                        else f"{tool_name}:{iteration + 1}"
                    )

                    # Validate args against the catalog schema (if any) before
                    # touching the Python tool. On failure, append a tool
                    # message describing the errors so the LLM retries with a
                    # corrected call. Cap retries per tool so a stuck model
                    # bails fast.
                    schema_errors = validate_tool_args(tool_name, tool_args)
                    if schema_errors:
                        validation_failures[tool_name] = (
                            validation_failures.get(tool_name, 0) + 1
                        )
                        attempts = validation_failures[tool_name]
                        exhausted = attempts > MAX_VALIDATION_RETRIES_PER_TOOL
                        failure_payload: dict[str, object] = {
                            "error": "invalid_arguments",
                            "tool_name": tool_name,
                            "details": schema_errors,
                            "attempt": attempts,
                        }
                        if exhausted:
                            failure_payload["reason"] = "max_validation_retries"
                            failure_payload["instruction"] = (
                                f"Do not call {tool_name} again this run. "
                                + "Tell the user the call could not be constructed."
                            )
                        logger.warning(
                            f"[{self.agent.name}] {tool_name} args failed schema"
                            + f" validation (attempt {attempts}): {schema_errors}"
                        )
                        get_execution_event_store().record_tool_call(
                            request_id=self.run_id,
                            memory_id=self.memory_id,
                            tool_call_id=resolved_call_id,
                            tool_name=tool_name,
                            tool_input=self._json_value(tool_args),
                        )
                        get_execution_event_store().record_tool_result(
                            request_id=self.run_id,
                            memory_id=self.memory_id,
                            tool_call_id=resolved_call_id,
                            tool_name=tool_name,
                            ok=False,
                            output=None,
                            error=json.dumps(failure_payload),
                        )
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": resolved_call_id,
                            "content": json.dumps(failure_payload),
                        }
                        messages = [*messages, tool_message]
                        continue

                    tools_executed.append(tool_name)
                    logger.info(f"[{self.agent.name}] Executing tool: {tool_name}")
                    get_execution_event_store().record_tool_call(
                        request_id=self.run_id,
                        memory_id=self.memory_id,
                        tool_call_id=resolved_call_id,
                        tool_name=tool_name,
                        tool_input=self._json_value(tool_args),
                    )
                    should_record_tool_memory = self._should_record_tool_memory(
                        tool_name
                    )
                    if should_record_tool_memory:
                        _ = self.memory_store.record_event(
                            type="tool_call",
                            text=f"Calling {tool_name}",
                            memory_id=self.memory_id,
                            idempotency_key=f"tool_call:{self.run_id}:{resolved_call_id}",
                            source="execution_agent",
                            metadata={"tool_name": tool_name, "arguments": tool_args},
                        )

                    success, result = await self._execute_tool(tool_name, tool_args)

                    if success:
                        logger.info(
                            f"[{self.agent.name}] Tool {tool_name} completed successfully"
                        )
                        record_payload = self._safe_json_dump(result)
                        if tool_name == "gmail_create_draft":
                            captured = self._capture_created_draft(tool_args, result)
                            if captured is not None:
                                created_drafts.append(captured)
                    else:
                        error_detail: object = (
                            cast(dict[str, object], result).get("error")
                            if isinstance(result, dict)
                            else str(result)
                        )
                        logger.warning(
                            f"[{self.agent.name}] Tool {tool_name} failed: {error_detail}"
                        )
                        record_payload = str(error_detail)
                    get_execution_event_store().record_tool_result(
                        request_id=self.run_id,
                        memory_id=self.memory_id,
                        tool_call_id=resolved_call_id,
                        tool_name=tool_name,
                        ok=success,
                        output=self._json_value(cast(object, result))
                        if success
                        else None,
                        error=None if success else record_payload,
                    )

                    self.agent.record_tool_execution(
                        tool_name, self._safe_json_dump(tool_args), record_payload
                    )
                    if should_record_tool_memory:
                        _ = self.memory_store.record_event(
                            type="tool_result",
                            text=f"{tool_name}: {record_payload[:500]}",
                            memory_id=self.memory_id,
                            idempotency_key=f"tool_result:{self.run_id}:{resolved_call_id}",
                            source="execution_agent",
                            metadata={
                                "tool_name": tool_name,
                                "success": success,
                                "result": result,
                            },
                        )

                    tool_message = {
                        "role": "tool",
                        "tool_call_id": resolved_call_id,
                        "content": self._format_tool_result(
                            tool_name, success, cast(object, result), tool_args
                        ),
                    }
                    messages = [*messages, tool_message]

            else:
                raise RuntimeError(
                    "Reached tool iteration limit without final response"
                )

            if created_drafts:
                drafts_block = self._render_created_drafts_block(created_drafts)
                if drafts_block:
                    final_response = (
                        f"{final_response.rstrip()}\n\n{drafts_block}"
                        if final_response
                        else drafts_block
                    )

            self.agent.record_response(final_response)
            _ = self.memory_store.record_event(
                type="execution_response",
                text=final_response,
                memory_id=self.memory_id,
                idempotency_key=f"execution_response:{self.run_id}",
                source="execution_agent",
            )

            return ExecutionResult(
                memory_id=self.memory_id,
                memory_title=self.memory_title,
                agent_name=self.agent.name,
                success=True,
                response=final_response,
                tools_executed=tools_executed,
            )

        except asyncio.CancelledError:
            # Cancellation is a distinct terminal state — use record_completed
            # so the run row transitions to a terminal status AND a run.failed
            # event flows through both per-turn and thread-scoped SSE
            # subscribers. Then re-raise so asyncio marks the task cancelled.
            logger.info(f"[{self.agent.name}] Execution cancelled")
            try:
                get_execution_event_store().record_completed(
                    request_id=self.run_id,
                    memory_id=self.memory_id,
                    title=self.memory_title,
                    ok=False,
                    response="cancelled by user",
                    error="cancelled",
                )
            except Exception as record_exc:  # pragma: no cover - defensive
                logger.warning(
                    "failed to emit cancellation event",
                    extra={
                        "request_id": self.run_id,
                        "error": str(record_exc),
                    },
                )
            raise
        except Exception as e:
            logger.error(f"[{self.agent.name}] Execution failed: {e}")
            error_msg = str(e)
            failure_text = f"Failed to complete task: {error_msg}"
            self.agent.record_response(f"Error: {error_msg}")
            _ = self.memory_store.record_event(
                type="execution_response",
                text=f"Error: {error_msg}",
                memory_id=self.memory_id,
                idempotency_key=f"execution_response:{self.run_id}",
                source="execution_agent",
                metadata={"error": error_msg},
            )

            return ExecutionResult(
                memory_id=self.memory_id,
                memory_title=self.memory_title,
                agent_name=self.agent.name,
                success=False,
                response=failure_text,
                error=error_msg,
            )

    # Execute OpenRouter API call with system prompt, messages, and optional tool schemas
    async def _make_llm_call(
        self,
        system_prompt: str,
        messages: Sequence[Mapping[str, object]],
        with_tools: bool,
    ) -> OpenRouterChatCompletion:
        """Make an LLM call."""
        tools_to_send = self.tool_schemas if with_tools else None
        logger.info(
            f"[{self.agent.name}] Calling LLM with model: {self.model}, tools: {len(tools_to_send) if tools_to_send else 0}"
        )
        return await request_chat_completion(
            model=self.model,
            messages=messages,
            system=system_prompt,
            api_key=self.api_key,
            tools=tools_to_send,
        )

    # Parse and validate tool calls from LLM response into structured format
    def _extract_tool_calls(
        self, raw_tools: Sequence[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        """Extract tool calls from an assistant message."""
        tool_calls: list[dict[str, object]] = []

        for tool in raw_tools:
            raw_function = tool.get("function")
            function: Mapping[str, object] = (
                cast(Mapping[str, object], raw_function)
                if isinstance(raw_function, Mapping)
                else {}
            )
            name = str(function.get("name") or "")
            raw_args = function.get("arguments") or ""
            args: object = raw_args

            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args = {}

            if name:
                tool_calls.append(
                    {
                        "id": tool.get("id"),
                        "name": name,
                        "arguments": args,
                    }
                )

        return tool_calls

    # Safely convert objects to JSON with fallback to string representation
    def _safe_json_dump(self, payload: object) -> str:
        """Serialize payload to JSON, falling back to string representation."""
        try:
            return json.dumps(payload, default=str)
        except TypeError:
            return str(payload)

    def _json_value(self, value: object) -> JsonValue:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, dict):
            d = cast(dict[object, object], value)
            return {str(k): self._json_value(v) for k, v in d.items()}
        if isinstance(value, list | tuple):
            seq = cast(list[object], value)
            return [self._json_value(item) for item in seq]
        return str(value)

    def _should_record_tool_memory(self, tool_name: str) -> bool:
        """Return whether a tool call/result is meaningful memory."""
        retrieval_only_tools = {
            "task_email_search",
        }
        return tool_name not in retrieval_only_tools

    # Format tool execution results into JSON structure for LLM consumption
    @staticmethod
    def _capture_created_draft(
        tool_args: Mapping[str, object],
        tool_result: object,
    ) -> dict[str, object] | None:
        """Pull to/subject/body off a successful gmail_create_draft call.

        Returns ``None`` if the args don't include the expected fields — we
        only surface drafts that have all three of recipient/subject/body.
        Body and subject are taken verbatim from the arguments the LLM
        passed (which Composio echoed back). draft_id is best-effort from
        the response payload but not required for UI rendering.
        """

        to = tool_args.get("recipient_email")
        subject = tool_args.get("subject")
        body = tool_args.get("body")
        if not (
            isinstance(to, str) and isinstance(subject, str) and isinstance(body, str)
        ):
            return None

        draft_id = ""
        if isinstance(tool_result, Mapping):
            tool_result_map = cast(Mapping[str, object], tool_result)
            data = tool_result_map.get("data")
            if isinstance(data, Mapping):
                data_map = cast(Mapping[str, object], data)
                candidate = data_map.get("response_data")
                if isinstance(candidate, Mapping):
                    candidate_map = cast(Mapping[str, object], candidate)
                    raw_id = candidate_map.get("id") or candidate_map.get("draft_id")
                    if isinstance(raw_id, str):
                        draft_id = raw_id
                raw_id = data_map.get("id") or data_map.get("draft_id")
                if not draft_id and isinstance(raw_id, str):
                    draft_id = raw_id

        draft: dict[str, object] = {
            "to": to,
            "subject": subject,
            "body": body,
            "draft_id": draft_id,
        }
        for key in ("cc", "bcc", "extra_recipients"):
            value = tool_args.get(key)
            if isinstance(value, list):
                value_list = cast(list[object], value)
                strings = [item for item in value_list if isinstance(item, str)]
                if strings:
                    draft[key] = strings
        for key in ("is_html", "thread_id", "attachment"):
            value = tool_args.get(key)
            if value is not None:
                draft[key] = value
        return draft

    @staticmethod
    def _render_created_drafts_block(drafts: Sequence[Mapping[str, object]]) -> str:
        """Render captured drafts as an XML block for the interaction agent.

        The interaction agent's system prompt expects exactly this shape and
        renders one ``send_draft`` tool call per ``<draft>`` element.
        """

        if not drafts:
            return ""

        lines: list[str] = ["<created_drafts>"]
        for draft in drafts:
            attrs = f'to="{_xml_attr(str(draft.get("to", "")))}" subject="{_xml_attr(str(draft.get("subject", "")))}"'
            for key in ("draft_id", "thread_id"):
                value = draft.get(key)
                if isinstance(value, str) and value:
                    attrs += f' {key}="{_xml_attr(value)}"'
            for key in ("cc", "bcc", "extra_recipients"):
                value = draft.get(key)
                if isinstance(value, list) and value:
                    attrs += (
                        f" {key}='{_xml_attr(json.dumps(value, ensure_ascii=False))}'"
                    )
            is_html = draft.get("is_html")
            if isinstance(is_html, bool):
                attrs += f' is_html="{str(is_html).lower()}"'
            attachment = draft.get("attachment")
            if isinstance(attachment, Mapping):
                attrs += f" attachment='{_xml_attr(json.dumps(attachment, ensure_ascii=False, default=str))}'"
            lines.append(f"  <draft {attrs}>")
            body = str(draft.get("body", ""))
            # XML-style body block. We do NOT escape the body content
            # because LLMs handle the raw text more reliably than escaped
            # entities, and the closing tag is unique enough not to collide.
            lines.append(f"    <body>{body}</body>")
            lines.append("  </draft>")
        lines.append("</created_drafts>")
        return "\n".join(lines)

    def _format_tool_result(
        self,
        tool_name: str,
        success: bool,
        result: object,
        arguments: dict[str, object],
    ) -> str:
        """Build a structured string for tool responses."""
        if success:
            shrunk_result = shrink_gmail_tool_result(tool_name, result)
            payload: dict[str, object] = {
                "tool": tool_name,
                "status": "success",
                "arguments": arguments,
                "result": shrunk_result,
            }
        else:
            error_detail: object = (
                cast(dict[str, object], result).get("error")
                if isinstance(result, dict)
                else str(result)
            )
            payload = {
                "tool": tool_name,
                "status": "error",
                "arguments": arguments,
                "error": error_detail,
            }
        return self._safe_json_dump(payload)

    # Execute tool function from registry with error handling and async support
    async def _execute_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> tuple[bool, object]:
        """Execute a tool. Returns (success, result)."""
        tool_func = self.tool_registry.get(tool_name)
        if not tool_func:
            return False, {"error": f"Unknown tool: {tool_name}"}

        try:
            raw = tool_func(**arguments)
            result: object = await raw if inspect.isawaitable(raw) else raw
            return True, result
        except Exception as e:
            return False, {"error": str(e)}
