from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import AsyncMock, patch

from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionResult
from server.agents.interaction_agent import tools as interaction_tools
from server.services.memory.store import MemoryStore


class _FakeExecutionLogs:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def record_request(self, memory_id: str, instructions: str) -> None:
        self.requests.append((memory_id, instructions))


class _FakeBatchManager:
    def __init__(self) -> None:
        self.submissions: list[dict[str, str]] = []

    async def execute_agent(
        self,
        memory_id: str,
        instructions: str,
        *,
        memory_title: str,
        request_id: str,
        notify_user: bool = True,
    ) -> ExecutionResult:
        self.submissions.append(
            {
                "memory_id": memory_id,
                "memory_title": memory_title,
                "instructions": instructions,
                "request_id": request_id,
                "notify_user": str(notify_user),
            }
        )
        return ExecutionResult(
            memory_id=memory_id,
            memory_title=memory_title,
            agent_name=memory_id,
            success=True,
            response="done",
            request_id=request_id,
        )


class _FakeExecutionEventStore:
    def __init__(self) -> None:
        self.submitted: list[dict[str, str | None]] = []

    def record_submitted(
        self,
        *,
        request_id: str,
        memory_id: str,
        title: str,
        instructions: str,
        parent_memory_id: str | None = None,
    ) -> None:
        self.submitted.append(
            {
                "request_id": request_id,
                "memory_id": memory_id,
                "title": title,
                "instructions": instructions,
                "parent_memory_id": parent_memory_id,
            }
        )

    def list_runs(self, *, limit: int = 100) -> list[object]:
        return []


class FanoutToolTests(unittest.IsolatedAsyncioTestCase):
    tmpdir: TemporaryDirectory[str] = cast(TemporaryDirectory[str], cast(object, None))
    store: MemoryStore = cast(MemoryStore, cast(object, None))
    fake_logs: _FakeExecutionLogs = cast(_FakeExecutionLogs, cast(object, None))
    fake_events: _FakeExecutionEventStore = cast(
        _FakeExecutionEventStore, cast(object, None)
    )
    fake_manager: _FakeBatchManager = cast(_FakeBatchManager, cast(object, None))
    _previous_manager: object = None

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.tmpdir.name) / "memory.db")
        self.fake_logs = _FakeExecutionLogs()
        self.fake_events = _FakeExecutionEventStore()
        self.fake_manager = _FakeBatchManager()
        self._previous_manager = interaction_tools._execution_batch_manager
        interaction_tools._execution_batch_manager = self.fake_manager

    def tearDown(self) -> None:
        interaction_tools._execution_batch_manager = self._previous_manager
        self.tmpdir.cleanup()

    async def test_fanout_creates_child_memories_and_submits_each(self) -> None:
        with patch.object(interaction_tools, "get_memory_store", return_value=self.store), patch.object(
            interaction_tools,
            "get_execution_agent_logs",
            return_value=self.fake_logs,
        ), patch.object(
            interaction_tools,
            "get_execution_event_store",
            return_value=self.fake_events,
        ), patch.object(
            interaction_tools,
            "get_active_gmail_user_id",
            return_value="gmail-user",
        ):
            result = interaction_tools.send_messages_to_agents(
                coordination_note="Send email batch",
                items=[
                    {
                        "task_name": "Email Alice: Hello",
                        "instructions": "Draft the email to alice@example.com.",
                    },
                    {
                        "task_name": "Email Bob: Hello",
                        "instructions": "Draft the email to bob@example.com.",
                    },
                    {
                        "task_name": "Email Carol: Hello",
                        "instructions": "Draft the email to carol@example.com.",
                    },
                ],
            )
            await asyncio.sleep(0)

        self.assertTrue(result.success)
        payload = result.payload
        assert isinstance(payload, dict)
        payload = cast(dict[str, object], payload)
        self.assertEqual(payload["submitted_count"], 3)
        parent_memory_id = payload["parent_memory_id"]
        assert isinstance(parent_memory_id, str)
        parent = self.store.get_memory(parent_memory_id)
        self.assertIsNotNone(parent)
        assert parent is not None

        children = payload["children"]
        assert isinstance(children, list)
        child_ids = [
            child["memory_id"]
            for child in children
            if isinstance(child, dict) and isinstance(child.get("memory_id"), str)
        ]
        self.assertEqual(
            sorted(link.value for link in parent.links if link.kind == "child_memory"),
            sorted(child_ids),
        )
        self.assertFalse(
            any(link.kind in {"gmail_thread", "gmail_draft", "gmail_message", "email_address"} for link in parent.links)
        )

        for child_id in child_ids:
            child = self.store.get_memory(child_id)
            self.assertIsNotNone(child)
            assert child is not None
            self.assertTrue(
                any(event.type == "execution_request" for event in child.recent_events),
                child_id,
            )

        self.assertEqual(len(self.fake_logs.requests), 3)
        self.assertEqual(len(self.fake_events.submitted), 3)
        self.assertEqual(len(self.fake_manager.submissions), 3)
        self.assertTrue(
            all(submission["notify_user"] == "False" for submission in self.fake_manager.submissions)
        )

    async def test_single_send_message_to_agent_still_submits(self) -> None:
        with patch.object(interaction_tools, "get_memory_store", return_value=self.store), patch.object(
            interaction_tools,
            "get_execution_agent_logs",
            return_value=self.fake_logs,
        ), patch.object(
            interaction_tools,
            "get_execution_event_store",
            return_value=self.fake_events,
        ), patch.object(
            interaction_tools,
            "get_active_gmail_user_id",
            return_value="gmail-user",
        ):
            result = interaction_tools.send_message_to_agent(
                task_name="Single task",
                instructions="Do one thing.",
            )
            await asyncio.sleep(0)

        self.assertTrue(result.success)
        payload = result.payload
        assert isinstance(payload, dict)
        self.assertEqual(payload["status"], "submitted")
        self.assertEqual(len(self.fake_logs.requests), 1)
        self.assertEqual(len(self.fake_events.submitted), 1)
        self.assertEqual(len(self.fake_manager.submissions), 1)
        self.assertEqual(self.fake_manager.submissions[0]["notify_user"], "False")


class ExecutionBatchManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_dispatches_without_waiting_for_all_pending(self) -> None:
        manager = ExecutionBatchManager()
        manager._dispatch_to_interaction_agent = AsyncMock()

        batch_id = await manager._register_pending_execution("mem-a", "A", "one", "req-a")
        await manager._register_pending_execution("mem-b", "B", "two", "req-b")
        await manager._register_pending_execution("mem-c", "C", "three", "req-c")

        await manager._complete_execution(
            batch_id,
            ExecutionResult("mem-a", "A", "mem-a", True, "sent", request_id="req-a"),
            "mem-a",
        )
        await manager._complete_execution(
            batch_id,
            ExecutionResult("mem-b", "B", "mem-b", True, "sent", request_id="req-b"),
            "mem-b",
        )

        self.assertEqual(manager._dispatch_to_interaction_agent.await_count, 2)
        self.assertIsNotNone(manager._batch_state)
        assert manager._batch_state is not None
        self.assertEqual(manager._batch_state.pending, 1)

    async def test_completion_can_skip_user_dispatch_for_panel_only_visibility(self) -> None:
        manager = ExecutionBatchManager()
        manager._dispatch_to_interaction_agent = AsyncMock()
        recorded_statuses: list[str] = []

        batch_id = await manager._register_pending_execution(
            "mem-a", "A", "one", "req-a", notify_user=False
        )
        with patch(
            "server.services.conversation.get_conversation_log",
            return_value=type(
                "FakeConversationLog",
                (),
                {"record_agent_message": lambda _, content: recorded_statuses.append(content)},
            )(),
        ):
            await manager._complete_execution(
                batch_id,
                ExecutionResult("mem-a", "A", "mem-a", True, "sent", request_id="req-a"),
                "mem-a",
                notify_user=False,
            )

        manager._dispatch_to_interaction_agent.assert_not_awaited()
        self.assertEqual(len(recorded_statuses), 1)
        self.assertIn("[SUCCESS] mem-a / A: sent", recorded_statuses[0])

    async def test_failure_and_success_results_dispatch_independently(self) -> None:
        manager = ExecutionBatchManager()
        manager._dispatch_to_interaction_agent = AsyncMock()

        batch_id = await manager._register_pending_execution("mem-a", "A", "one", "req-a")
        await manager._register_pending_execution("mem-b", "B", "two", "req-b")
        await manager._register_pending_execution("mem-c", "C", "three", "req-c")

        results = [
            ExecutionResult("mem-a", "A", "mem-a", True, "sent", request_id="req-a"),
            ExecutionResult("mem-b", "B", "mem-b", False, "failed", error="boom", request_id="req-b"),
            ExecutionResult("mem-c", "C", "mem-c", True, "sent", request_id="req-c"),
        ]
        for result in results:
            await manager._complete_execution(batch_id, result, result.memory_id)

        self.assertEqual(manager._dispatch_to_interaction_agent.await_count, 3)
        payloads = [
            call.args[0]
            for call in manager._dispatch_to_interaction_agent.await_args_list
        ]
        self.assertIn("[FAILED] mem-b / B: failed", payloads[1])
        self.assertIn("request_id: req-b", payloads[1])
        self.assertIn("error: boom", payloads[1])
        self.assertIsNone(manager._batch_state)


if __name__ == "__main__":
    unittest.main()
