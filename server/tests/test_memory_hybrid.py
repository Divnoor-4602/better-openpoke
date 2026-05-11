from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services.memory.hybrid_search import exact_link_candidates
from server.services.memory.indexer import serialize_event, serialize_memory
from server.services.memory.store import MemoryLink, MemoryStore


class MemoryHybridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "memory.db"
        self.store = MemoryStore(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_memory_event_and_links_enqueue_indexing(self) -> None:
        memory = self.store.create_memory(
            kind="gmail",
            title="Invoice follow-up",
            summary="Follow up with Pat",
            links=[MemoryLink(kind="gmail_thread", value="thread-12345678")],
        )
        self.store.update_memory(memory.memory_id, summary="Updated")
        event = self.store.record_event(
            type="email_seen",
            text="Pat sent the invoice",
            memory_id=memory.memory_id,
            links=[MemoryLink(kind="email_address", value="pat@example.com")],
        )
        self.store.add_links(
            memory.memory_id,
            [MemoryLink(kind="gmail_draft", value="draft-87654321")],
            event.event_id,
        )

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT entity_type, entity_id, operation, status FROM memory_index_queue"
            ).fetchall()

        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(
            any(row["entity_type"] == "memory" and row["entity_id"] == memory.memory_id for row in rows)
        )
        self.assertTrue(
            any(row["entity_type"] == "event" and row["entity_id"] == event.event_id for row in rows)
        )
        self.assertTrue(all(row["operation"] == "upsert" for row in rows))
        self.assertTrue(all(row["status"] == "pending" for row in rows))

    def test_serializers_include_text_links_and_metadata(self) -> None:
        memory = self.store.create_memory(
            kind="gmail",
            title="Contract renewal",
            summary="Renewal with Dana",
            metadata={"source": "test"},
            links=[MemoryLink(kind="gmail_thread", value="thread-abc12345")],
        )
        event = self.store.record_event(
            type="email_seen",
            text="Dana asked about renewal pricing",
            memory_id=memory.memory_id,
            metadata={"importance": "high"},
            links=[MemoryLink(kind="email_address", value="dana@example.com")],
        )

        with self._connect() as conn:
            memory_doc = serialize_memory(conn, memory.memory_id)
            event_doc = serialize_event(conn, event.event_id)

        self.assertIsNotNone(memory_doc)
        self.assertIsNotNone(event_doc)
        assert memory_doc is not None
        assert event_doc is not None
        self.assertIn("Contract renewal", memory_doc.text)
        self.assertIn("thread-abc12345", memory_doc.text)
        self.assertEqual(memory_doc.metadata["entity_type"], "memory")
        self.assertEqual(memory_doc.metadata["memory_id"], memory.memory_id)
        self.assertIn("Dana asked about renewal pricing", event_doc.text)
        self.assertEqual(event_doc.metadata["entity_type"], "event")
        self.assertEqual(event_doc.metadata["memory_id"], memory.memory_id)

    def test_exact_link_lookup_prioritizes_gmail_and_email_matches(self) -> None:
        memory = self.store.create_memory(
            kind="gmail",
            title="Travel booking",
            links=[
                MemoryLink(kind="gmail_thread", value="thread-99990000"),
                MemoryLink(kind="email_address", value="ops@example.com"),
            ],
        )
        with self._connect() as conn:
            candidates = exact_link_candidates(
                conn,
                "Find the ops@example.com thread thread-99990000",
            )

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].memory_id, memory.memory_id)
        self.assertGreaterEqual(candidates[0].exact_priority, 3)

    def test_search_falls_back_to_sqlite_lexical_without_pinecone_config(self) -> None:
        memory = self.store.create_memory(
            kind="user_task",
            title="Prepare board deck",
            summary="Slides for Q2 board meeting",
        )

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=False):
            results = self.store.search("board slides", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].memory.memory_id, memory.memory_id)
        self.assertIn("title", results[0].reason)

    def test_render_memory_context_can_prefer_query_relevant_events(self) -> None:
        memory = self.store.create_memory(kind="user_task", title="Vendor search")
        self.store.record_event(
            type="note",
            text="The user rejected Acme because pricing was too high",
            memory_id=memory.memory_id,
        )
        self.store.record_event(
            type="note",
            text="Latest status is waiting for procurement",
            memory_id=memory.memory_id,
        )

        context = self.store.render_memory_context(
            memory.memory_id,
            query="why was acme rejected",
            event_limit=1,
        )

        self.assertIn("pricing was too high", context)
        self.assertNotIn("waiting for procurement", context)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


if __name__ == "__main__":
    unittest.main()
