from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.services.memory.gmail import record_gmail_tool_result
from server.services.memory.hybrid_search import exact_link_candidates
from server.services.memory.indexer import MemoryIndexer, serialize_event, serialize_memory
from server.services.memory.store import MemoryLink, MemoryStore


class MemoryHybridTests(unittest.TestCase):
    tmpdir: tempfile.TemporaryDirectory[str] | None = None
    _db_path: Path | None = None
    _store: MemoryStore | None = None

    @property
    def db_path(self) -> Path:
        assert self._db_path is not None
        return self._db_path

    @property
    def store(self) -> MemoryStore:
        assert self._store is not None
        return self._store

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self.tmpdir.name) / "memory.db"
        self._store = MemoryStore(self._db_path)

    def tearDown(self) -> None:
        assert self.tmpdir is not None
        self.tmpdir.cleanup()

    def test_memory_event_and_links_enqueue_idempotent_indexing(self) -> None:
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
                """
                SELECT idempotency_key, entity_type, entity_id, operation, status
                FROM memory_index_queue
                ORDER BY entity_type, entity_id
                """
            ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertTrue(
            any(row["entity_type"] == "memory" and row["entity_id"] == memory.memory_id for row in rows)
        )
        self.assertTrue(
            any(row["entity_type"] == "event" and row["entity_id"] == event.event_id for row in rows)
        )
        self.assertTrue(all(row["operation"] == "upsert" for row in rows))
        self.assertTrue(all(row["status"] == "pending" for row in rows))
        self.assertEqual(
            len({row["idempotency_key"] for row in rows}),
            len(rows),
        )

    def test_indexer_batches_embeddings_and_upsert(self) -> None:
        memory = self.store.create_memory(
            kind="gmail",
            title="Batch indexing",
            summary="Batch this memory",
        )
        event = self.store.record_event(
            type="note",
            text="Batch this event too",
            memory_id=memory.memory_id,
        )
        fake_pc = _FakePinecone()
        fake_index = _FakeIndex()

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=True), patch(
            "server.services.memory.indexer._pinecone_index",
            return_value=(fake_pc, fake_index),
        ):
            synced = MemoryIndexer(self.db_path).sync_pending(limit=10)

        self.assertEqual(synced, 2)
        self.assertEqual(len(fake_pc.embed_calls), 2)
        self.assertEqual(fake_pc.embed_calls[0]["count"], 2)
        self.assertEqual(fake_pc.embed_calls[1]["count"], 2)
        self.assertEqual(len(fake_index.upserts), 1)
        self.assertEqual(len(fake_index.upserts[0]["vectors"]), 2)
        with self._connect() as conn:
            statuses = [
                row["status"]
                for row in conn.execute("SELECT status FROM memory_index_queue").fetchall()
            ]
        self.assertEqual(statuses, ["done", "done"])

    def test_indexer_failure_backs_off_and_marks_dead_after_max_attempts(self) -> None:
        memory = self.store.create_memory(
            kind="gmail",
            title="Retry indexing",
            summary="This upsert will fail",
        )
        fake_pc = _FakePinecone()
        fake_index = _FakeIndex(fail_upsert=True)

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=True), patch(
            "server.services.memory.indexer._pinecone_index",
            return_value=(fake_pc, fake_index),
        ):
            synced = MemoryIndexer(self.db_path).sync_pending(limit=10)

        self.assertEqual(synced, 0)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, status, attempts, available_at FROM memory_index_queue WHERE entity_id = ?",
                (memory.memory_id,),
            ).fetchone()
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["attempts"], 1)
            self.assertIsNotNone(row["available_at"])
            conn.execute(
                """
                UPDATE memory_index_queue
                SET attempts = max_attempts - 1,
                    available_at = '2000-01-01T00:00:00.000Z'
                WHERE id = ?
                """,
                (row["id"],),
            )
            conn.commit()

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=True), patch(
            "server.services.memory.indexer._pinecone_index",
            return_value=(fake_pc, fake_index),
        ):
            MemoryIndexer(self.db_path).sync_pending(limit=10)

        with self._connect() as conn:
            dead = conn.execute(
                "SELECT status, available_at FROM memory_index_queue WHERE entity_id = ?",
                (memory.memory_id,),
            ).fetchone()
            self.assertEqual(dead["status"], "dead")
            self.assertIsNone(dead["available_at"])
            stats = MemoryIndexer(self.db_path).queue_stats()
            self.assertEqual(stats["dead"], 1)

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=True), patch(
            "server.services.memory.indexer._pinecone_index",
            return_value=(fake_pc, fake_index),
        ):
            MemoryIndexer(self.db_path).sync_pending(limit=10)
        self.assertEqual(len(fake_index.upserts), 2)

    def test_indexer_delete_operation_deletes_pinecone_vector(self) -> None:
        fake_pc = _FakePinecone()
        fake_index = _FakeIndex()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_index_queue (
                    id, idempotency_key, entity_type, entity_id, operation, version,
                    status, attempts, available_at, max_attempts, created_at, updated_at
                ) VALUES (
                    'idx_delete', 'delete:memory:mem_deleted', 'memory', 'mem_deleted',
                    'delete', '1', 'pending', 0, '2000-01-01T00:00:00.000Z', 5,
                    '2000-01-01T00:00:00.000Z', '2000-01-01T00:00:00.000Z'
                )
                """
            )
            conn.commit()

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=True), patch(
            "server.services.memory.indexer._pinecone_index",
            return_value=(fake_pc, fake_index),
        ):
            synced = MemoryIndexer(self.db_path).sync_pending(limit=10)

        self.assertEqual(synced, 1)
        self.assertEqual(fake_index.deletes, [{"ids": ["memory:mem_deleted"], "namespace": "openpoke"}])
        with self._connect() as conn:
            status = conn.execute(
                "SELECT status FROM memory_index_queue WHERE id = 'idx_delete'"
            ).fetchone()["status"]
            self.assertEqual(status, "done")

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

    def test_gmail_actions_create_thread_memory_not_parent_task_memory(self) -> None:
        parent = self.store.create_memory(
            kind="user_task",
            title="Send three emails",
            summary="Broad parent execution task",
        )

        first = record_gmail_tool_result(
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            result={
                "data": {
                    "id": "draft-a",
                    "message": {"threadId": "thread-a"},
                },
                "successful": True,
            },
            arguments={
                "recipient_email": "alice@example.com",
                "subject": "Hello Alice",
            },
            memory_id=parent.memory_id,
            store=self.store,
        )
        second = record_gmail_tool_result(
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            result={
                "data": {
                    "id": "draft-b",
                    "message": {"threadId": "thread-b"},
                },
                "successful": True,
            },
            arguments={
                "recipient_email": "bob@example.com",
                "subject": "Hello Bob",
            },
            memory_id=parent.memory_id,
            store=self.store,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0], parent.memory_id)
        self.assertNotEqual(second[0], parent.memory_id)
        self.assertNotEqual(first[0], second[0])

        parent_refreshed = self.store.get_memory(parent.memory_id)
        assert parent_refreshed is not None
        self.assertFalse(
            any(link.kind == "gmail_thread" for link in parent_refreshed.links)
        )
        self.assertEqual(
            sorted(link.value for link in parent_refreshed.links if link.kind == "child_memory"),
            sorted([first[0], second[0]]),
        )

        alice = self.store.get_memory(first[0])
        bob = self.store.get_memory(second[0])
        assert alice is not None
        assert bob is not None
        self.assertTrue(
            any(link.kind == "email_address" and link.value == "alice@example.com" for link in alice.links)
        )
        self.assertTrue(
            any(link.kind == "email_address" and link.value == "bob@example.com" for link in bob.links)
        )
        self.assertIn("alice@example.com", alice.title)
        self.assertIn("Hello Alice", alice.title)
        self.assertIn("bob@example.com", bob.title)
        self.assertIn("Hello Bob", bob.title)

    def test_gmail_send_draft_reuses_draft_thread_memory(self) -> None:
        parent = self.store.create_memory(
            kind="user_task",
            title="Send Alice email",
        )
        [draft_memory_id] = record_gmail_tool_result(
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            result={
                "data": {
                    "id": "draft-a",
                    "message": {"threadId": "thread-a"},
                },
                "successful": True,
            },
            arguments={
                "recipient_email": "alice@example.com",
                "subject": "Hello Alice",
            },
            memory_id=parent.memory_id,
            store=self.store,
        )

        [sent_memory_id] = record_gmail_tool_result(
            tool_name="GMAIL_SEND_DRAFT",
            result={
                "data": {
                    "id": "message-a",
                    "threadId": "thread-a",
                },
                "successful": True,
            },
            arguments={"draft_id": "draft-a"},
            memory_id=parent.memory_id,
            store=self.store,
        )

        self.assertEqual(sent_memory_id, draft_memory_id)
        memory = self.store.get_memory(sent_memory_id)
        assert memory is not None
        self.assertIn("alice@example.com", memory.title)
        self.assertIn("Hello Alice", memory.title)
        event_types = [event.type for event in memory.recent_events]
        self.assertIn("gmail_draft_created", event_types)
        self.assertIn("gmail_draft_sent", event_types)

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

    def test_default_search_logs_do_not_include_event_text(self) -> None:
        memory = self.store.create_memory(kind="user_task", title="Private note")
        self.store.record_event(
            type="note",
            text="Sensitive event snippet",
            memory_id=memory.memory_id,
        )

        with patch("server.services.memory.indexer.pinecone_enabled", return_value=False), self.assertLogs(
            "openpoke", level="INFO"
        ) as captured:
            self.store.search("private sensitive", limit=3)

        self.assertNotIn("Sensitive event snippet", "\n".join(captured.output))

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

class _FakeInference:
    def __init__(self, parent: "_FakePinecone") -> None:
        self._parent = parent

    def embed(self, *, model, inputs, parameters):
        self._parent.embed_calls.append({"model": model, "count": len(inputs)})
        if model == "llama-text-embed-v2":
            return [{"values": [0.1, 0.2, 0.3]} for _ in inputs]
        return [
            {"sparse_indices": [1, 5, 9], "sparse_values": [0.3, 0.2, 0.1]}
            for _ in inputs
        ]


class _FakePinecone:
    def __init__(self) -> None:
        self.embed_calls = []
        self.inference = _FakeInference(self)


class _FakeIndex:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.upserts = []
        self.deletes = []
        self.fail_upsert = fail_upsert

    def upsert(self, *, vectors, namespace):
        if self.fail_upsert:
            self.upserts.append({"vectors": vectors, "namespace": namespace})
            raise RuntimeError("upsert failed")
        self.upserts.append({"vectors": vectors, "namespace": namespace})

    def delete(self, *, ids, namespace):
        self.deletes.append({"ids": ids, "namespace": namespace})


if __name__ == "__main__":
    unittest.main()
