"""Simplified Execution Agent Runtime."""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ...config import get_settings
from ...logging_config import logger
from ...openrouter_client import JsonValue, OpenRouterChatCompletion, request_chat_completion
from ...services.execution import get_execution_event_store
from ...services.memory import get_memory_store
from .agent import ExecutionAgent
from .tools import get_tool_registry, get_tool_schemas


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

    MAX_TOOL_ITERATIONS = 8

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
            (
                f'memory_id="{self.memory_id}" title="{self.memory_title}" '
                f'context_chars="{len(memory_context)}" debug_content="{include_content}"'
            ),
        ]
        if memory is not None:
            lines.append(
                f'loaded_memory kind="{memory.kind}" links="{len(memory.links)}" '
                f'recent_events="{len(memory.recent_events)}" updated_at="{memory.updated_at}"'
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
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": instructions}
            ]
            tools_executed: list[str] = []
            final_response: str | None = None

            for iteration in range(self.MAX_TOOL_ITERATIONS):
                logger.info(
                    f"[{self.agent.name}] Requesting plan (iteration {iteration + 1})"
                )
                response = await self._make_llm_call(
                    system_prompt, messages, with_tools=True
                )
                assistant_message = response.get("choices", [{}])[0].get("message", {})

                if not assistant_message:
                    raise RuntimeError(
                        "LLM response did not include an assistant message"
                    )

                raw_tool_calls = assistant_message.get("tool_calls", []) or []
                parsed_tool_calls = self._extract_tool_calls(raw_tool_calls)

                assistant_entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_message.get("content", "") or "",
                }
                if raw_tool_calls:
                    assistant_entry["tool_calls"] = raw_tool_calls
                messages.append(assistant_entry)

                if not parsed_tool_calls:
                    final_response = assistant_entry["content"] or "No action required."
                    break

                for tool_call in parsed_tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})
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
                        messages.append(tool_message)
                        continue

                    tools_executed.append(tool_name)
                    logger.info(f"[{self.agent.name}] Executing tool: {tool_name}")
                    resolved_call_id = call_id or f"{tool_name}:{iteration + 1}"
                    get_execution_event_store().record_tool_call(
                        request_id=self.run_id,
                        memory_id=self.memory_id,
                        tool_call_id=resolved_call_id,
                        tool_name=tool_name,
                        input=tool_args,
                    )
                    should_record_tool_memory = self._should_record_tool_memory(
                        tool_name
                    )
                    if should_record_tool_memory:
                        self.memory_store.record_event(
                            type="tool_call",
                            text=f"Calling {tool_name}",
                            memory_id=self.memory_id,
                            idempotency_key=f"tool_call:{self.run_id}:{call_id or tool_name}",
                            source="execution_agent",
                            metadata={"tool_name": tool_name, "arguments": tool_args},
                        )

                    success, result = await self._execute_tool(tool_name, tool_args)

                    if success:
                        logger.info(
                            f"[{self.agent.name}] Tool {tool_name} completed successfully"
                        )
                        record_payload = self._safe_json_dump(result)
                    else:
                        error_detail = (
                            result.get("error")
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
                        output=self._json_value(result) if success else None,
                        error=None if success else record_payload,
                    )

                    self.agent.record_tool_execution(
                        tool_name, self._safe_json_dump(tool_args), record_payload
                    )
                    if should_record_tool_memory:
                        self.memory_store.record_event(
                            type="tool_result",
                            text=f"{tool_name}: {record_payload[:500]}",
                            memory_id=self.memory_id,
                            idempotency_key=f"tool_result:{self.run_id}:{call_id or tool_name}",
                            source="execution_agent",
                            metadata={
                                "tool_name": tool_name,
                                "success": success,
                                "result": result,
                            },
                        )

                    tool_message = {
                        "role": "tool",
                        "tool_call_id": call_id or tool_name,
                        "content": self._format_tool_result(
                            tool_name, success, result, tool_args
                        ),
                    }
                    messages.append(tool_message)

            else:
                raise RuntimeError(
                    "Reached tool iteration limit without final response"
                )

            if final_response is None:
                raise RuntimeError("LLM did not return a final response")

            self.agent.record_response(final_response)
            self.memory_store.record_event(
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

        except Exception as e:
            logger.error(f"[{self.agent.name}] Execution failed: {e}")
            error_msg = str(e)
            failure_text = f"Failed to complete task: {error_msg}"
            self.agent.record_response(f"Error: {error_msg}")
            self.memory_store.record_event(
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
        self, system_prompt: str, messages: list[dict[str, Any]], with_tools: bool
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
    ) -> list[dict[str, Any]]:
        """Extract tool calls from an assistant message."""
        tool_calls: list[dict[str, Any]] = []

        for tool in raw_tools:
            raw_function = tool.get("function", {})
            function = raw_function if isinstance(raw_function, Mapping) else {}
            name = function.get("name", "")
            args = function.get("arguments", "")

            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
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
            return {str(key): self._json_value(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self._json_value(item) for item in value]
        return str(value)

    def _should_record_tool_memory(self, tool_name: str) -> bool:
        """Return whether a tool call/result is meaningful memory."""
        retrieval_only_tools = {
            "task_email_search",
        }
        return tool_name not in retrieval_only_tools

    # Format tool execution results into JSON structure for LLM consumption
    def _format_tool_result(
        self,
        tool_name: str,
        success: bool,
        result: object,
        arguments: dict[str, Any],
    ) -> str:
        """Build a structured string for tool responses."""
        if success:
            payload: dict[str, Any] = {
                "tool": tool_name,
                "status": "success",
                "arguments": arguments,
                "result": result,
            }
        else:
            error_detail = (
                result.get("error") if isinstance(result, dict) else str(result)
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
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, object]:
        """Execute a tool. Returns (success, result)."""
        tool_func = self.tool_registry.get(tool_name)
        if not tool_func:
            return False, {"error": f"Unknown tool: {tool_name}"}

        try:
            result = tool_func(**arguments)
            if inspect.isawaitable(result):
                result = await result
            return True, result
        except Exception as e:
            return False, {"error": str(e)}
