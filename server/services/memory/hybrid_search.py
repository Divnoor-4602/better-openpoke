"""Hybrid memory search over SQLite exact matches and Pinecone candidates."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ...config import get_settings
from ...logging_config import logger
from .indexer import DENSE_EMBED_MODEL, SPARSE_EMBED_MODEL, pinecone_enabled

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
MEMORY_ID_PATTERN = re.compile(r"\bmem_[a-f0-9]{16,}\b", re.I)
LONG_ID_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]{8,}\b")


@dataclass
class SearchCandidate:
    """Raw event or memory candidate before final ranking/packing."""

    entity_type: str
    memory_id: Optional[str]
    event_id: Optional[str] = None
    score: float = 0.0
    exact_priority: int = 0
    sources: set[str] = field(default_factory=set)
    reason_parts: set[str] = field(default_factory=set)
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> tuple[str, str]:
        if self.event_id:
            return ("event", self.event_id)
        return ("memory", self.memory_id or "")

    @property
    def sort_score(self) -> float:
        return (self.exact_priority * 1000.0) + self.score


def hybrid_candidates(
    db_path: Any,
    query: str,
    *,
    top_k: int = 60,
) -> list[SearchCandidate]:
    candidates: list[SearchCandidate] = []
    with _connect(db_path) as conn:
        candidates.extend(exact_link_candidates(conn, query))
        candidates.extend(pinecone_candidates(query, top_k=top_k))
        candidates.extend(recent_unindexed_candidates(conn))
    return merge_candidates(candidates)


def exact_link_candidates(
    conn: sqlite3.Connection, query: str
) -> list[SearchCandidate]:
    identifiers = extract_identifiers(query)
    lowered_query = query.lower()
    candidates: list[SearchCandidate] = []

    for memory_id in identifiers["memory_id"]:
        row = conn.execute(
            "SELECT * FROM memories WHERE lower(memory_id) = ?",
            (memory_id.lower(),),
        ).fetchone()
        if row is not None:
            candidates.append(
                SearchCandidate(
                    entity_type="memory",
                    memory_id=str(row["memory_id"]),
                    score=250.0,
                    exact_priority=5,
                    sources={"sqlite_exact"},
                    reason_parts={"exact memory_id"},
                    text=f"{row['title']} {row['summary'] or ''}",
                )
            )

    link_rows = conn.execute(
        """
        SELECT l.*, e.text AS event_text
        FROM links l
        LEFT JOIN events e ON e.event_id = l.event_id
        """
    ).fetchall()
    for row in link_rows:
        kind = str(row["kind"])
        value = str(row["value"])
        value_lower = value.lower()
        priority = _exact_link_priority(kind, value_lower, identifiers, lowered_query)
        if priority <= 0:
            continue
        candidates.append(
            SearchCandidate(
                entity_type="event" if row["event_id"] else "memory",
                memory_id=row["memory_id"],
                event_id=row["event_id"],
                score=priority * 50.0,
                exact_priority=priority,
                sources={"sqlite_exact"},
                reason_parts={f"exact {kind}"},
                text=str(row["event_text"] or value),
                metadata={"link_kind": kind, "link_value": value},
            )
        )
    return candidates


def pinecone_candidates(query: str, *, top_k: int = 60) -> list[SearchCandidate]:
    settings = get_settings()
    if not pinecone_enabled():
        return []

    api_key = settings.pinecone_api_key
    index_host = settings.pinecone_index_host
    if api_key is None or index_host is None:
        return []

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)
        index = pc.Index(host=index_host)
        dense = pc.inference.embed(
            model=DENSE_EMBED_MODEL,
            inputs=[query],
            parameters={"input_type": "query", "truncate": "END"},
        )[0]
        sparse = pc.inference.embed(
            model=SPARSE_EMBED_MODEL,
            inputs=[query],
            parameters={"input_type": "query", "truncate": "END"},
        )[0]
        response = index.query(
            namespace=settings.pinecone_namespace,
            top_k=top_k,
            vector=dense["values"],
            sparse_vector={
                "indices": sparse["sparse_indices"],
                "values": sparse["sparse_values"],
            },
            include_values=False,
            include_metadata=True,
        )
    except Exception as exc:  # pragma: no cover - external service failure
        logger.warning(
            "Pinecone hybrid memory search failed", extra={"error": str(exc)}
        )
        return []

    matches = _response_matches(response)
    candidates: list[SearchCandidate] = []
    for match in matches:
        metadata = dict(_get(match, "metadata", {}) or {})
        entity_type = str(metadata.get("entity_type") or "memory")
        event_id = metadata.get("event_id")
        memory_id = metadata.get("memory_id")
        candidates.append(
            SearchCandidate(
                entity_type=entity_type,
                memory_id=str(memory_id) if memory_id else None,
                event_id=str(event_id) if event_id else None,
                score=float(_get(match, "score", 0.0) or 0.0),
                sources={"pinecone_hybrid"},
                reason_parts={"hybrid dense+sparse"},
                text=str(metadata.get("text") or ""),
                metadata=metadata,
            )
        )
    return candidates


def recent_unindexed_candidates(
    conn: sqlite3.Connection, *, limit: int = 24
) -> list[SearchCandidate]:
    candidates: list[SearchCandidate] = []
    rows = conn.execute(
        """
        SELECT entity_type, entity_id
        FROM memory_index_queue
        WHERE status IN ('pending', 'failed')
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    seen = {(str(row["entity_type"]), str(row["entity_id"])) for row in rows}

    for entity_type, entity_id in seen:
        if entity_type == "memory":
            row = conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (entity_id,),
            ).fetchone()
            if row is not None:
                candidates.append(
                    SearchCandidate(
                        entity_type="memory",
                        memory_id=entity_id,
                        score=5.0,
                        sources={"sqlite_unindexed"},
                        reason_parts={"recent unindexed memory"},
                        text=f"{row['title']} {row['summary'] or ''}",
                    )
                )
        elif entity_type == "event":
            row = conn.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (entity_id,),
            ).fetchone()
            if row is not None:
                candidates.append(
                    SearchCandidate(
                        entity_type="event",
                        memory_id=row["memory_id"],
                        event_id=entity_id,
                        score=5.0,
                        sources={"sqlite_unindexed"},
                        reason_parts={"recent unindexed event"},
                        text=str(row["text"]),
                    )
                )

    recent_memory_rows = conn.execute(
        "SELECT * FROM memories ORDER BY updated_at DESC LIMIT 8"
    ).fetchall()
    for row in recent_memory_rows:
        candidates.append(
            SearchCandidate(
                entity_type="memory",
                memory_id=str(row["memory_id"]),
                score=1.0,
                sources={"sqlite_recent"},
                reason_parts={"recent memory"},
                text=f"{row['title']} {row['summary'] or ''}",
            )
        )
    return candidates


def merge_candidates(candidates: Iterable[SearchCandidate]) -> list[SearchCandidate]:
    merged: dict[tuple[str, str], SearchCandidate] = {}
    for candidate in candidates:
        if not candidate.memory_id and not candidate.event_id:
            continue
        key = candidate.dedupe_key
        existing = merged.get(key)
        if existing is None:
            merged[key] = candidate
            continue
        existing.score = max(existing.score, candidate.score)
        existing.exact_priority = max(existing.exact_priority, candidate.exact_priority)
        existing.sources.update(candidate.sources)
        existing.reason_parts.update(candidate.reason_parts)
        if not existing.text and candidate.text:
            existing.text = candidate.text
        existing.metadata.update(candidate.metadata)
    return sorted(merged.values(), key=lambda item: item.sort_score, reverse=True)


def extract_identifiers(query: str) -> dict[str, set[str]]:
    emails = {match.lower() for match in EMAIL_PATTERN.findall(query)}
    memory_ids = {match for match in MEMORY_ID_PATTERN.findall(query)}
    long_ids = {
        match
        for match in LONG_ID_PATTERN.findall(query)
        if any(ch.isdigit() for ch in match) and len(match) >= 8
    }
    return {
        "email_address": emails,
        "memory_id": memory_ids,
        "long_id": long_ids,
    }


def _exact_link_priority(
    kind: str,
    value_lower: str,
    identifiers: dict[str, set[str]],
    lowered_query: str,
) -> int:
    if kind in {"gmail_thread", "gmail_message", "gmail_draft"}:
        if value_lower in lowered_query or value_lower in {
            value.lower() for value in identifiers["long_id"]
        }:
            return 4
    if kind == "email_address" and value_lower in identifiers["email_address"]:
        return 3
    if value_lower in {value.lower() for value in identifiers["long_id"]}:
        return 2
    return 0


def _response_matches(response: Any) -> list[Any]:
    if isinstance(response, dict):
        return list(response.get("matches") or [])
    return list(getattr(response, "matches", []) or [])


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _connect(db_path: Any) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
