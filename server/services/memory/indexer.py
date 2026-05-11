"""Pinecone indexing helpers for memory records and events."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from ...config import get_settings
from ...logging_config import logger

DENSE_EMBED_MODEL = "llama-text-embed-v2"
SPARSE_EMBED_MODEL = "pinecone-sparse-english-v0"


@dataclass(frozen=True)
class PineconeDocument:
    """Serialized memory/event payload ready for embedding and upsert."""

    id: str
    entity_type: str
    entity_id: str
    text: str
    metadata: dict[str, Any]


def pinecone_enabled() -> bool:
    settings = get_settings()
    return (
        settings.memory_search_backend == "pinecone_hybrid"
        and bool(settings.pinecone_api_key)
        and bool(settings.pinecone_index_host)
    )


def serialize_memory(conn: sqlite3.Connection, memory_id: str) -> Optional[PineconeDocument]:
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
    pinecone_metadata = {
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


def serialize_event(conn: sqlite3.Connection, event_id: str) -> Optional[PineconeDocument]:
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
    pinecone_metadata = {
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

    def __init__(self, db_path: Any) -> None:
        self._db_path = db_path

    async def sync_pending_async(self, *, limit: int = 50) -> int:
        return await asyncio.to_thread(self.sync_pending, limit=limit)

    def sync_pending(self, *, limit: int = 50) -> int:
        if not pinecone_enabled():
            return 0
        try:
            pc, index = _pinecone_index()
        except Exception as exc:  # pragma: no cover - depends on optional package/config
            logger.warning("Pinecone index unavailable", extra={"error": str(exc)})
            return 0

        synced = 0
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_index_queue
                WHERE status IN ('pending', 'failed')
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            for queue_row in rows:
                try:
                    doc = _document_for_queue_row(conn, queue_row)
                    if doc is None:
                        _mark_done(conn, queue_row["id"])
                        continue
                    vector = _embed_document(pc, doc)
                    index.upsert(vectors=[vector], namespace=get_settings().pinecone_namespace)
                    _mark_done(conn, queue_row["id"])
                    synced += 1
                except Exception as exc:  # pragma: no cover - external service failure
                    _mark_failed(conn, queue_row["id"], str(exc))
                    logger.warning(
                        "Pinecone memory indexing failed",
                        extra={
                            "queue_id": queue_row["id"],
                            "entity_type": queue_row["entity_type"],
                            "entity_id": queue_row["entity_id"],
                            "error": str(exc),
                        },
                    )
            conn.commit()
        return synced


def _document_for_queue_row(
    conn: sqlite3.Connection, row: sqlite3.Row
) -> Optional[PineconeDocument]:
    if row["operation"] != "upsert":
        return None
    if row["entity_type"] == "memory":
        return serialize_memory(conn, str(row["entity_id"]))
    if row["entity_type"] == "event":
        return serialize_event(conn, str(row["entity_id"]))
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


def _embed_document(pc: Any, doc: PineconeDocument) -> dict[str, Any]:
    dense = pc.inference.embed(
        model=DENSE_EMBED_MODEL,
        inputs=[doc.text],
        parameters={"input_type": "passage", "truncate": "END"},
    )[0]
    sparse = pc.inference.embed(
        model=SPARSE_EMBED_MODEL,
        inputs=[doc.text],
        parameters={"input_type": "passage", "truncate": "END"},
    )[0]
    return {
        "id": doc.id,
        "values": dense["values"],
        "sparse_values": {
            "indices": sparse["sparse_indices"],
            "values": sparse["sparse_values"],
        },
        "metadata": doc.metadata,
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


def _compact_mapping(label: str, payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    return f"{label}: " + json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


def _metadata_links(links: Iterable[sqlite3.Row]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
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


def _flatten_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flattened[f"meta_{key}"] = value
    return flattened


def _clean_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
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


def _load_json(payload: Any) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(str(payload))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _connect(db_path: Any) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _mark_done(conn: sqlite3.Connection, queue_id: str) -> None:
    conn.execute(
        """
        UPDATE memory_index_queue
        SET status = 'done', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ?
        """,
        (queue_id,),
    )


def _mark_failed(conn: sqlite3.Connection, queue_id: str, error: str) -> None:
    conn.execute(
        """
        UPDATE memory_index_queue
        SET status = 'failed',
            attempts = attempts + 1,
            last_error = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ?
        """,
        (error[:1000], queue_id),
    )
