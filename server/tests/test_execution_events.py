from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from server.services.execution.event_store import ExecutionEventStore


class ExecutionEventStoreTests(unittest.TestCase):
    tmpdir: TemporaryDirectory[str] = cast(TemporaryDirectory[str], cast(object, None))
    store: ExecutionEventStore = cast(ExecutionEventStore, cast(object, None))

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = ExecutionEventStore(Path(self.tmpdir.name) / "execution_events.db")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_records_run_with_ordered_ai_sdk_style_parts(self) -> None:
        self.store.record_submitted(
            request_id="req-1",
            memory_id="mem-1",
            parent_memory_id="mem-parent",
            title="Email Alice",
            instructions="Draft an email.",
        )
        self.store.record_started(
            request_id="req-1",
            memory_id="mem-1",
            title="Email Alice",
        )
        self.store.record_tool_call(
            request_id="req-1",
            memory_id="mem-1",
            tool_call_id="tool-1",
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            tool_input={"recipient_email": "alice@example.com"},
        )
        self.store.record_tool_result(
            request_id="req-1",
            memory_id="mem-1",
            tool_call_id="tool-1",
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            ok=True,
            output={"draft_id": "draft-a"},
        )
        self.store.record_completed(
            request_id="req-1",
            memory_id="mem-1",
            title="Email Alice",
            ok=True,
            response="Draft created.",
        )

        [run] = self.store.list_runs()
        self.assertEqual(run["requestId"], "req-1")
        self.assertEqual(run["memoryId"], "mem-1")
        self.assertEqual(run["parentMemoryId"], "mem-parent")
        self.assertEqual(run["status"], "completed")
        self.assertIs(run["ok"], True)
        self.assertEqual(
            [part["type"] for part in run["parts"]],
            ["status", "status", "tool-call", "tool-result", "agent-response", "status"],
        )
        self.assertEqual(run["parts"][2]["state"], "input-available")
        self.assertEqual(run["parts"][3]["state"], "output-available")
        self.assertEqual(run["parts"][3]["output"], {"draft_id": "draft-a"})

    def test_records_failed_tool_and_failed_run(self) -> None:
        self.store.record_submitted(
            request_id="req-2",
            memory_id="mem-2",
            title="Email Bob",
            instructions="Draft an email.",
        )
        self.store.record_tool_result(
            request_id="req-2",
            memory_id="mem-2",
            tool_call_id="tool-2",
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            ok=False,
            error="Gmail unavailable",
        )
        self.store.record_completed(
            request_id="req-2",
            memory_id="mem-2",
            title="Email Bob",
            ok=False,
            response="Failed.",
            error="Gmail unavailable",
        )

        [run] = self.store.list_runs()
        self.assertEqual(run["status"], "failed")
        self.assertIs(run["ok"], False)
        error_parts = [part for part in run["parts"] if part["state"] == "output-error"]
        self.assertEqual(len(error_parts), 2)
        self.assertEqual(error_parts[0]["error"], "Gmail unavailable")


if __name__ == "__main__":
    unittest.main()
