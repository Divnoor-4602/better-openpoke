"""Pinecone indexing helpers for memory records and events."""
# pyright: reportAny=false, reportExplicitAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportUnusedFunction=false

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from os import PathLike
from time import perf_counter
from typing import Any, TypeAlias, cast

from ...config import get_settings
from ...logging_config import logger

DENSE_EMBED_MODEL = "llama-text-embed-v2"
SPARSE_EMBED_MODEL = "pinecone-sparse-english-v0"
SQLitePath: TypeAlias = str | bytes | PathLike[str] | PathLike[bytes]


@dataclass(frozen=True)
class PineconeDocument:
    """Serialized memory/event payload ready for embedding and upsert."""

    id: str
    entity_type: str
    entity_id: str
    text: str
    metadata: dict[str, object]


def pinecone_enabled() -> bool:
    settings = get_settings()
    return (
        settings.memory_search_backend == "pinecone_hybrid"
        and bool(settings.pinecone_api_key)
        and bool(settings.pinecone_index_host)
    )


def serialize_memory(
    conn: sqlite3.Connection, memory_id: str
) -> PineconeDocument | None:
    row = conn.execute(
        "SELECT * FROM memories WHERE memory_id = ?",
        (memory_id,),
    ).fetchone()
    if row is None:
        return None

    links = _links_for_memory(conn, memory_id)
    latest_events = conn.execute(
        """
        SELECT * FROM events
        WHERE memory_id = ?
        ORDER BY COALESCE(timestamp, recorded_at) DESC
        LIMIT 8
        """,
        (memory_id,),
    ).fetchall()
    metadata = _load_json(row["metadata_json"])
    text_parts = [
        f"Memory title: {row['title']}",
        f"Memory summary: {row['summary'] or ''}",
        f"Kind: {row['kind']}",
        _compact_mapping("Metadata", metadata),
        _compact_links(links),
        _compact_events(latest_events),
    ]
    pinecone_metadata: dict[str, object] = {
        "entity_type": "memory",
        "memory_id": memory_id,
        "kind": row["kind"],
        "updated_at": row["updated_at"],
        "created_at": row["created_at"],
        "text": _join_parts(text_parts),
    }
    pinecone_metadata.update(_metadata_links(links))
    pinecone_metadata.update(_flatten_metadata(metadata))
    return PineconeDocument(
        id=f"memory:{memory_id}",
        entity_type="memory",
        entity_id=memory_id,
        text=str(pinecone_metadata["text"]),
        metadata=_clean_metadata(pinecone_metadata),
    )


def serialize_event(conn: sqlite3.Connection, event_id: str) -> PineconeDocument | None:
    row = conn.execute(
        "SELECT * FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        return None

    links = _links_for_event(conn, event_id)
    metadata = _load_json(row["metadata_json"])
    text_parts = [
        f"Event type: {row['type']}",
        f"Event text: {row['text']}",
        f"Source: {row['source'] or ''}",
        f"Timestamp: {row['timestamp'] or row['recorded_at']}",
        _compact_mapping("Metadata", metadata),
        _compact_links(links),
    ]
    pinecone_metadata: dict[str, object] = {
        "entity_type": "event",
        "event_id": event_id,
        "memory_id": row["memory_id"],
        "type": row["type"],
        "source": row["source"],
        "timestamp": row["timestamp"],
        "recorded_at": row["recorded_at"],
        "text": _join_parts(text_parts),
    }
    pinecone_metadata.update(_metadata_links(links))
    pinecone_metadata.update(_flatten_metadata(metadata))
    return PineconeDocument(
        id=f"event:{event_id}",
        entity_type="event",
        entity_id=event_id,
        text=str(pinecone_metadata["text"]),
        metadata=_clean_metadata(pinecone_metadata),
    )


class MemoryIndexer:
    """Sync pending memory_index_queue rows into Pinecone."""

    def __init__(self, db_path: SQLitePath) -> None:
        self._db_path = db_path

    async def sync_pending_async(self, *, limit: int = 50) -> int:
        return await asyncio.to_thread(self.sync_pending, limit=limit)

    def sync_pending(self, *, limit: int = 50) -> int:
        if not pinecone_enabled():
            return 0

        synced = 0
        with closing(_connect(self._db_path)) as conn:
            rows = _claim_rows(conn, limit)
            if not rows:
                return 0

            try:
                pc, index = _pinecone_index()
            except (
                Exception
            ) as exc:  # pragma: no cover - depends on optional package/config
                _release_claimed_rows(conn, rows, str(exc))
                conn.commit()
                logger.warning("Pinecone index unavailable", extra={"error": str(exc)})
                return 0

            done_without_upsert: list[str] = []
            documents_by_id: dict[str, PineconeDocument] = {}
            queue_ids_by_doc_id: dict[str, list[str]] = {}
            delete_ids: list[str] = []
            delete_queue_ids: list[str] = []
            for queue_row in rows:
                if queue_row["operation"] == "delete":
                    vector_id = _vector_id_for_queue_row(queue_row)
                    if vector_id is None:
                        done_without_upsert.append(str(queue_row["id"]))
                    else:
                        delete_ids.append(vector_id)
                        delete_queue_ids.append(str(queue_row["id"]))
                    continue
                try:
                    doc = _document_for_queue_row(conn, queue_row)
                    if doc is None:
                        done_without_upsert.append(str(queue_row["id"]))
                        continue
                except Exception as exc:  # pragma: no cover - external service failure
                    _mark_failed(conn, queue_row["id"], str(exc))
                    logger.warning(
                        "Memory indexing serialization failed",
                        extra={
                            "queue_id": queue_row["id"],
                            "entity_type": queue_row["entity_type"],
                            "entity_id": queue_row["entity_id"],
                            "error": str(exc),
                        },
                    )
                    continue
                documents_by_id[doc.id] = doc
                queue_ids_by_doc_id.setdefault(doc.id, []).append(str(queue_row["id"]))

            if done_without_upsert:
                _mark_many_done(conn, done_without_upsert)

            if delete_ids:
                try:
                    started = perf_counter()
                    _delete_vectors(index, delete_ids)
                    _mark_many_done(conn, delete_queue_ids)
                    synced += len(delete_queue_ids)
                    logger.info(
                        "Pinecone memory delete batch completed",
                        extra={
                            "queue_rows": len(delete_queue_ids),
                            "records": len(delete_ids),
                            "delete_ms": _elapsed_ms(started),
                        },
                    )
                except Exception as exc:  # pragma: no cover - external service failure
                    _mark_many_failed(conn, delete_queue_ids, str(exc))
                    logger.warning(
                        "Pinecone memory delete batch failed",
                        extra={
                            "queue_rows": len(delete_queue_ids),
                            "records": len(delete_ids),
                            "error": str(exc),
                        },
                    )

            documents = list(documents_by_id.values())
            if documents:
                queue_ids = [
                    queue_id
                    for doc_id in documents_by_id
                    for queue_id in queue_ids_by_doc_id.get(doc_id, [])
                ]
                try:
                    started = perf_counter()
                    vectors = _embed_documents(pc, documents)
                    embed_ms = _elapsed_ms(started)
                    started = perf_counter()
                    index.upsert(
                        vectors=vectors,
                        namespace=get_settings().pinecone_namespace,
                    )
                    _mark_many_done(conn, queue_ids)
                    synced += len(queue_ids)
                    logger.info(
                        "Pinecone memory indexing batch completed",
                        extra={
                            "queue_rows": len(queue_ids),
                            "records": len(vectors),
                            "embed_ms": embed_ms,
                            "upsert_ms": _elapsed_ms(started),
                        },
                    )
                except Exception as exc:  # pragma: no cover - external service failure
                    _mark_many_failed(conn, queue_ids, str(exc))
                    logger.warning(
                        "Pinecone memory indexing batch failed",
                        extra={
                            "queue_rows": len(queue_ids),
                            "records": len(documents),
                            "error": str(exc),
                        },
                    )
            conn.commit()
        return synced

    def queue_stats(self) -> dict[str, object]:
        with closing(_connect(self._db_path)) as conn:
            return queue_stats(conn)


def _document_for_queue_row(
    conn: sqlite3.Connection, row: sqlite3.Row
) -> PineconeDocument | None:
    if row["operation"] != "upsert":
        return None
    if row["entity_type"] == "memory":
        return serialize_memory(conn, str(row["entity_id"]))
    if row["entity_type"] == "event":
        return serialize_event(conn, str(row["entity_id"]))
    return None


def _vector_id_for_queue_row(row: sqlite3.Row) -> str | None:
    if row["entity_type"] == "memory":
        return f"memory:{row['entity_id']}"
    if row["entity_type"] == "event":
        return f"event:{row['entity_id']}"
    return None


def _pinecone_index() -> tuple[Any, Any]:
    from pinecone import Pinecone

    settings = get_settings()
    api_key = settings.pinecone_api_key
    index_host = settings.pinecone_index_host
    if api_key is None or index_host is None:
        raise RuntimeError("Pinecone index is not configured")

    pc = Pinecone(api_key=api_key)
    return pc, pc.Index(host=index_host)


def _embed_document(pc: Any, doc: PineconeDocument) -> dict[str, object]:
    return _embed_documents(pc, [doc])[0]


def _embed_documents(pc: Any, docs: list[PineconeDocument]) -> list[dict[str, object]]:
    if not docs:
        return []
    texts = [doc.text for doc in docs]
    started = perf_counter()
    dense_embeddings = pc.inference.embed(
        model=DENSE_EMBED_MODEL,
        inputs=texts,
        parameters={"input_type": "passage", "truncate": "END"},
    )
    dense_ms = _elapsed_ms(started)
    started = perf_counter()
    sparse_embeddings = pc.inference.embed(
        model=SPARSE_EMBED_MODEL,
        inputs=texts,
        parameters={"input_type": "passage", "truncate": "END"},
    )
    logger.info(
        "Pinecone memory embeddings completed",
        extra={
            "records": len(docs),
            "dense_embed_ms": dense_ms,
            "sparse_embed_ms": _elapsed_ms(started),
        },
    )
    vectors: list[dict[str, object]] = []
    for doc, dense, sparse in zip(
        docs, dense_embeddings, sparse_embeddings, strict=True
    ):
        vectors.append(
            {
                "id": doc.id,
                "values": _embedding_values(dense),
                "sparse_values": _sparse_values(sparse),
                "metadata": doc.metadata,
            }
        )
    return vectors


def _delete_vectors(index: Any, ids: list[str]) -> None:
    if not ids:
        return
    index.delete(ids=ids, namespace=get_settings().pinecone_namespace)


def _embedding_values(embedding: object) -> list[float]:
    if isinstance(embedding, Mapping):
        return list(cast(Iterable[float], embedding["values"]))
    return list(cast(Iterable[float], getattr(embedding, "values")))


def _sparse_values(embedding: object) -> dict[str, list[object]]:
    if isinstance(embedding, Mapping):
        indices = embedding.get("sparse_indices") or embedding.get("indices")
        values = embedding.get("sparse_values") or embedding.get("values")
    else:
        indices = getattr(embedding, "sparse_indices", None) or getattr(
            embedding, "indices"
        )
        values = getattr(embedding, "sparse_values", None) or getattr(
            embedding, "values"
        )
    return {
        "indices": list(cast(Iterable[object], indices)),
        "values": list(cast(Iterable[object], values)),
    }


def _links_for_memory(conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM links WHERE memory_id = ? ORDER BY created_at DESC",
        (memory_id,),
    ).fetchall()


def _links_for_event(conn: sqlite3.Connection, event_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM links WHERE event_id = ? ORDER BY created_at DESC",
        (event_id,),
    ).fetchall()


def _compact_links(links: Iterable[sqlite3.Row]) -> str:
    values = [f"{row['kind']}: {row['value']}" for row in links]
    return "Links: " + "; ".join(values[:24]) if values else ""


def _compact_events(events: Iterable[sqlite3.Row]) -> str:
    values = [
        f"{row['timestamp'] or row['recorded_at']} {row['type']}: {row['text']}"
        for row in events
    ]
    return "Recent events: " + " | ".join(values) if values else ""


def _compact_mapping(label: str, payload: dict[str, object]) -> str:
    if not payload:
        return ""
    return f"{label}: " + json.dumps(
        payload, ensure_ascii=False, default=str, sort_keys=True
    )


def _metadata_links(links: Iterable[sqlite3.Row]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    values_by_kind: dict[str, list[str]] = {}
    for row in links:
        kind = str(row["kind"])
        value = str(row["value"])
        values_by_kind.setdefault(kind, [])
        if value not in values_by_kind[kind]:
            values_by_kind[kind].append(value)
    for kind, values in values_by_kind.items():
        if kind in {"gmail_thread", "gmail_message", "gmail_draft", "email_address"}:
            metadata[kind] = values[:12]
        else:
            metadata[f"link_{kind}"] = values[:12]
    return metadata


def _flatten_metadata(payload: dict[str, object]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flattened[f"meta_{key}"] = value
    return flattened


def _clean_metadata(payload: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, list):
            string_values = [str(item) for item in value if item is not None]
            if string_values:
                cleaned[key] = string_values
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
    return cleaned


def _join_parts(parts: Iterable[str]) -> str:
    return "\n".join(part for part in parts if part).strip()


def _load_json(payload: object) -> dict[str, object]:
    if not payload:
        return {}
    try:
        data = json.loads(str(payload))
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], data) if isinstance(data, dict) else {}


def _connect(db_path: SQLitePath) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _claim_rows(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    conn.execute("BEGIN IMMEDIATE")
    rows = conn.execute(
        """
        SELECT * FROM memory_index_queue
        WHERE (
                status IN ('pending', 'failed')
                AND COALESCE(available_at, updated_at, created_at)
                    <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
              )
           OR (
                status = 'processing'
                AND updated_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-10 minutes')
           )
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        conn.commit()
        return []
    ids = [str(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"""
        UPDATE memory_index_queue
        SET status = 'processing',
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id IN ({placeholders})
        """,
        ids,
    )
    conn.commit()
    return rows


def _mark_done(conn: sqlite3.Connection, queue_id: str) -> None:
    _mark_many_done(conn, [queue_id])


def _mark_failed(conn: sqlite3.Connection, queue_id: str, error: str) -> None:
    _mark_many_failed(conn, [queue_id], error)


def _release_claimed_rows(
    conn: sqlite3.Connection, rows: list[sqlite3.Row], error: str
) -> None:
    if not rows:
        return
    queue_ids = [str(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in queue_ids)
    conn.execute(
        f"""
        UPDATE memory_index_queue
        SET status = CASE
                WHEN attempts + 1 >= max_attempts THEN 'dead'
                ELSE 'failed'
            END,
            attempts = attempts + 1,
            last_error = ?,
            available_at = CASE
                WHEN attempts + 1 >= max_attempts THEN NULL
                ELSE strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '+30 seconds')
            END,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id IN ({placeholders})
        """,
        [error[:1000], *queue_ids],
    )


def _mark_many_done(conn: sqlite3.Connection, queue_ids: list[str]) -> None:
    if not queue_ids:
        return
    placeholders = ",".join("?" for _ in queue_ids)
    conn.execute(
        f"""
        UPDATE memory_index_queue
        SET status = 'done',
            last_error = NULL,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id IN ({placeholders})
        """,
        queue_ids,
    )


def _mark_many_failed(
    conn: sqlite3.Connection, queue_ids: list[str], error: str
) -> None:
    if not queue_ids:
        return
    placeholders = ",".join("?" for _ in queue_ids)
    conn.execute(
        f"""
        UPDATE memory_index_queue
        SET status = CASE
                WHEN attempts + 1 >= max_attempts THEN 'dead'
                ELSE 'failed'
            END,
            attempts = attempts + 1,
            last_error = ?,
            available_at = CASE
                WHEN attempts + 1 >= max_attempts THEN NULL
                ELSE strftime(
                    '%Y-%m-%dT%H:%M:%fZ',
                    'now',
                    '+' || MIN(480, 30 * (1 << attempts)) || ' seconds'
                )
            END,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id IN ({placeholders})
        """,
        [error[:1000], *queue_ids],
    )


def queue_stats(conn: sqlite3.Connection) -> dict[str, object]:
    counts = {
        str(row["status"]): int(row["count"])
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM memory_index_queue
            GROUP BY status
            """
        ).fetchall()
    }
    oldest = conn.execute(
        """
        SELECT created_at
        FROM memory_index_queue
        WHERE status IN ('pending', 'failed', 'processing')
        ORDER BY created_at ASC
        LIMIT 1
        """
    ).fetchone()
    failed = conn.execute(
        """
        SELECT id, entity_type, entity_id, attempts, last_error
        FROM memory_index_queue
        WHERE status = 'failed'
        ORDER BY updated_at DESC
        LIMIT 3
        """
    ).fetchall()
    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "failed": counts.get("failed", 0),
        "dead": counts.get("dead", 0),
        "done": counts.get("done", 0),
        "oldest_active_age_seconds": _age_seconds(oldest["created_at"])
        if oldest
        else 0,
        "recent_failures": [
            {
                "queue_id": row["id"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "attempts": row["attempts"],
                "error": _truncate(str(row["last_error"] or ""), 180),
            }
            for row in failed
        ],
    }


def _age_seconds(timestamp: str) -> int:
    try:
        if timestamp.endswith("Z"):
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(
            0,
            int(
                (
                    datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
                ).total_seconds()
            ),
        )
    except ValueError:
        return 0


def _truncate(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)
