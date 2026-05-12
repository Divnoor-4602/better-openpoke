"""Coordinate execution agents and dispatch their results to the interaction agent."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from ...logging_config import logger
from ...services.execution import get_execution_event_store
from .runtime import ExecutionAgentRuntime, ExecutionResult

_running_tasks: set[asyncio.Task[object]] = set()


@dataclass
class PendingExecution:
    """Track a pending execution request."""

    request_id: str
    memory_id: str
    memory_title: str
    instructions: str
    batch_id: str
    notify_user: bool = True
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class _BatchState:
    """Collect results for a single interaction-agent turn."""

    batch_id: str
    created_at: datetime = field(default_factory=datetime.now)
    pending: int = 0
    results: list[ExecutionResult] = field(default_factory=list)


class ExecutionBatchManager:
    """Run execution agents and deliver each outcome independently."""

    # Initialize batch manager with timeout and coordination state for execution agents
    def __init__(self, timeout_seconds: int = 90) -> None:
        self.timeout_seconds = timeout_seconds
        self._pending: dict[str, PendingExecution] = {}
        self._batch_lock = asyncio.Lock()
        self._batch_state: _BatchState | None = None

    # Run execution agent with timeout handling and batch coordination for interaction agent
    async def execute_agent(
        self,
        agent_name: str,
        instructions: str,
        memory_title: str | None = None,
        request_id: str | None = None,
        notify_user: bool = True,
    ) -> ExecutionResult:
        """Execute an agent asynchronously and dispatch its result."""

        memory_id = agent_name
        resolved_title = memory_title or memory_id
        if not request_id:
            request_id = str(uuid.uuid4())

        batch_id = await self._register_pending_execution(
            memory_id, resolved_title, instructions, request_id, notify_user
        )

        try:
            logger.info(f"[{memory_id}] Execution started")
            get_execution_event_store().record_started(
                request_id=request_id,
                memory_id=memory_id,
                title=resolved_title,
            )
            runtime = ExecutionAgentRuntime(
                agent_name=memory_id,
                memory_title=resolved_title,
                run_id=request_id,
            )
            result = await asyncio.wait_for(
                runtime.execute(instructions),
                timeout=self.timeout_seconds,
            )
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"[{memory_id}] Execution finished: {status}")
        except asyncio.TimeoutError:
            logger.error(
                f"[{memory_id}] Execution timed out after {self.timeout_seconds}s"
            )
            result = ExecutionResult(
                memory_id=memory_id,
                memory_title=resolved_title,
                agent_name=memory_id,
                success=False,
                response=f"Execution timed out after {self.timeout_seconds} seconds",
                error="Timeout",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(f"[{memory_id}] Execution failed unexpectedly")
            result = ExecutionResult(
                memory_id=memory_id,
                memory_title=resolved_title,
                agent_name=memory_id,
                success=False,
                response=f"Execution failed: {exc}",
                error=str(exc),
            )
        finally:
            self._pending.pop(request_id, None)

        result.request_id = request_id
        get_execution_event_store().record_completed(
            request_id=request_id,
            memory_id=memory_id,
            title=resolved_title,
            ok=result.success,
            response=result.response,
            error=result.error,
        )
        await self._complete_execution(batch_id, result, memory_id, notify_user)
        return result

    # Add execution request to current batch or create new batch if none exists
    async def _register_pending_execution(
        self,
        memory_id: str,
        memory_title: str,
        instructions: str,
        request_id: str,
        notify_user: bool = True,
    ) -> str:
        """Attach a new execution to the active batch, opening one when required."""

        async with self._batch_lock:
            if self._batch_state is None:
                batch_id = str(uuid.uuid4())
                self._batch_state = _BatchState(batch_id=batch_id)
            else:
                batch_id = self._batch_state.batch_id

            self._batch_state.pending += 1
            self._pending[request_id] = PendingExecution(
                request_id=request_id,
                memory_id=memory_id,
                memory_title=memory_title,
                instructions=instructions,
                batch_id=batch_id,
                notify_user=notify_user,
            )

            return batch_id

    # Store execution result and notify interaction agent immediately
    async def _complete_execution(
        self,
        batch_id: str,
        result: ExecutionResult,
        agent_name: str,
        notify_user: bool = True,
    ) -> None:
        """Record the execution result and dispatch without waiting for siblings."""

        dispatch_payload: str | None = (
            self._format_execution_payload(result) if notify_user else None
        )

        async with self._batch_lock:
            state = self._batch_state
            if state is None or state.batch_id != batch_id:
                logger.warning(f"[{agent_name}] Dropping result for unknown batch")
                return

            state.results.append(result)
            state.pending -= 1

            if state.pending == 0:
                memory_ids = [entry.memory_id for entry in state.results]
                logger.info(f"Execution batch completed: {', '.join(memory_ids)}")
                self._batch_state = None

        if dispatch_payload:
            await self._dispatch_to_interaction_agent(dispatch_payload)
        else:
            self._record_status_for_interaction_context(result)

    # Return list of currently pending execution requests for monitoring purposes
    def get_pending_executions(self) -> list[dict[str, str | float]]:
        """Expose pending executions for observability."""

        return [
            {
                "request_id": pending.request_id,
                "memory_id": pending.memory_id,
                "memory_title": pending.memory_title,
                "batch_id": pending.batch_id,
                "created_at": pending.created_at.isoformat(),
                "elapsed_seconds": (
                    datetime.now() - pending.created_at
                ).total_seconds(),
            }
            for pending in self._pending.values()
        ]

    # Clean up all pending executions and batch state on shutdown
    async def shutdown(self) -> None:
        """Clear pending bookkeeping (no background work remains)."""

        self._pending.clear()
        async with self._batch_lock:
            self._batch_state = None

    # Format one execution result into a message for the interaction agent
    def _format_execution_payload(self, result: ExecutionResult) -> str:
        """Render one execution result into the interaction-agent format."""

        status = "SUCCESS" if result.success else "FAILED"
        response_text = (result.response or "(no response provided)").strip()
        error_line = f"\nerror: {result.error}" if result.error else ""
        request_id = getattr(result, "request_id", None) or ""
        request_line = f"\nrequest_id: {request_id}" if request_id else ""
        return (
            f"[{status}] {result.memory_id} / {result.memory_title}: {response_text}"
            f"{request_line}{error_line}"
        )

    # Forward one execution result to interaction agent for user response generation
    async def _dispatch_to_interaction_agent(self, payload: str) -> None:
        """Send an execution summary to the interaction agent."""

        from importlib import import_module

        module = import_module("server.agents.interaction_agent.runtime")
        InteractionAgentRuntime = module.InteractionAgentRuntime

        runtime = InteractionAgentRuntime()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(runtime.handle_agent_message(payload))
            return

        task = loop.create_task(runtime.handle_agent_message(payload))
        _running_tasks.add(task)
        task.add_done_callback(_running_tasks.discard)

    def _record_status_for_interaction_context(self, result: ExecutionResult) -> None:
        """Store worker status in hidden conversation context without chatting."""

        try:
            from ...services.conversation import get_conversation_log
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "conversation log unavailable for execution status",
                extra={"error": str(exc), "memory_id": result.memory_id},
            )
            return

        get_conversation_log().record_agent_message(self._format_execution_payload(result))
