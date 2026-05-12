from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from server.agents.interaction_agent.runtime import InteractionResult
from server.routes import execution
from server.services.execution import ExecutionEventPayload


def _agent_response_payload() -> ExecutionEventPayload:
    return {
        "requestId": "req-1",
        "memoryId": "mem-1",
        "parentMemoryId": None,
        "title": "Task",
        "event": {
            "id": 1,
            "type": "agent-response",
            "state": "output-available",
            "toolCallId": None,
            "toolName": None,
            "text": "Execution finished.",
            "input": None,
            "output": None,
            "error": None,
            "createdAt": "2026-05-12T00:00:00-0700",
        },
    }


class ExecutionStreamReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_replayed_execution_events_do_not_generate_interaction_reply(
        self,
    ) -> None:
        handle_agent_message = AsyncMock()
        with patch.object(
            execution.InteractionAgentRuntime,
            "handle_agent_message",
            handle_agent_message,
        ):
            chunks = [
                chunk
                async for chunk in execution._stream_execution_event_payload(
                    _agent_response_payload(),
                    generate_interaction=False,
                )
            ]

        self.assertEqual(len(chunks), 1)
        self.assertIn("data-execution-event", chunks[0])
        handle_agent_message.assert_not_awaited()

    async def test_live_execution_events_can_generate_interaction_reply(self) -> None:
        handle_agent_message = AsyncMock(
            return_value=InteractionResult(
                success=True,
                response="Done.",
            )
        )
        with patch.object(
            execution.InteractionAgentRuntime,
            "handle_agent_message",
            handle_agent_message,
        ):
            chunks = [
                chunk
                async for chunk in execution._stream_execution_event_payload(
                    _agent_response_payload(),
                    generate_interaction=True,
                )
            ]

        self.assertGreater(len(chunks), 1)
        self.assertIn("data-execution-event", chunks[0])
        self.assertTrue(any("text-delta" in chunk for chunk in chunks))
        handle_agent_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
