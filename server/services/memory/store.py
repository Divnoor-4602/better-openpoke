"""SQLite-backed memory contexts, events, links, and lexical search."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from ...logging_config import logger
from ...utils.timezones import now_in_user_timezone

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_MEMORY_DB_PATH = _DATA_DIR / "memory.db"
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")


@dataclass(frozen=True)
class MemoryLink:
    """A stable external or semantic identifier attached to memory."""

    kind: str
    value: str
    label: Optional[str] = None


@dataclass(frozen=True)
class MemoryEvent:
    """One compact structured event stored in memory."""

    event_id: str
    memory_id: Optional[str]
    idempotency_key: Optional[str]
    type: str
    timestamp: Optional[str]
    recorded_at: str
    source: Optional[str]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    links: list[MemoryLink] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryRecord:
    """A reusable context group for execution agents."""

    memory_id: str
    kind: str
    title: str
    summary: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    links: list[MemoryLink] = field(default_factory=list)
    recent_events: list[MemoryEvent] = field(default_factory=list)


@dataclass(frozen=True)
class MemorySearchResult:
    """Ranked memory match returned to prompts and tools."""

    memory: MemoryRecord
    score: float
    confidence: str
    reason: str


class MemoryStore:
    """Persistence and retrieval for memory contexts."""

    def __init__(self, db_path: Path = _MEMORY_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def create_memory(
        self,
        *,
        kind: str,
        title: str,
        summary: str = "",
        metadata: Optional[dict[str, Any]] = None,
        links: Optional[Iterable[MemoryLink | dict[str, Any]]] = None,
    ) -> MemoryRecord:
        memory_id = self._new_id("mem")
        timestamp = self._now()
        normalized_links = self._normalize_links(links or [])

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    memory_id, kind, title, summary, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    kind,
                    title,
                    summary,
                    timestamp,
                    timestamp,
                    self._dump_json(metadata or {}),
                ),
            )
            for link in normalized_links:
                self._insert_link(conn, memory_id, None, link, timestamp)
            conn.commit()

        return self.get_memory(memory_id)  # type: ignore[return-value]

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                return None
            return self._memory_from_row(conn, row)

    def update_memory(
        self,
        memory_id: str,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[MemoryRecord]:
        """Update memory display fields without creating a new memory."""
        timestamp = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            if existing is None:
                return None

            existing_metadata = self._load_json(existing["metadata_json"])
            if metadata:
                existing_metadata.update(metadata)

            conn.execute(
                """
                UPDATE memories
                SET title = COALESCE(?, title),
                    summary = COALESCE(?, summary),
                    metadata_json = ?,
                    updated_at = ?
                WHERE memory_id = ?
                """,
                (
                    title,
                    summary,
                    self._dump_json(existing_metadata),
                    timestamp,
                    memory_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            return self._memory_from_row(conn, row)

    def find_memory_by_link(self, *, kind: str, value: str) -> Optional[MemoryRecord]:
        normalized_value = str(value).strip()
        if not normalized_value:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT m.*
                FROM memories m
                JOIN links l ON l.memory_id = m.memory_id
                WHERE l.kind = ? AND l.value = ?
                ORDER BY m.updated_at DESC
                LIMIT 1
                """,
                (kind, normalized_value),
            ).fetchone()
            if row is None:
                return None
            return self._memory_from_row(conn, row)

    def find_event_by_link(
        self,
        *,
        kind: str,
        value: str,
        event_type: Optional[str] = None,
    ) -> Optional[MemoryEvent]:
        """Return the newest event attached to a stable link."""
        normalized_value = str(value).strip()
        if not normalized_value:
            return None

        query = """
            SELECT e.*
            FROM events e
            JOIN links l ON l.event_id = e.event_id
            WHERE l.kind = ? AND l.value = ?
        """
        params: list[Any] = [kind, normalized_value]
        if event_type:
            query += " AND e.type = ?"
            params.append(event_type)
        query += " ORDER BY COALESCE(e.timestamp, e.recorded_at) DESC LIMIT 1"

        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
            if row is None:
                return None
            return self._event_from_row(conn, row)

    def ensure_memory_for_links(
        self,
        *,
        kind: str,
        title: str,
        summary: str = "",
        metadata: Optional[dict[str, Any]] = None,
        links: Optional[Iterable[MemoryLink | dict[str, Any]]] = None,
    ) -> MemoryRecord:
        normalized_links = self._normalize_links(links or [])
        for link in normalized_links:
            if link.kind in {"gmail_thread", "gmail_message"}:
                existing = self.find_memory_by_link(kind=link.kind, value=link.value)
                if existing is not None:
                    self.add_links(existing.memory_id, normalized_links)
                    return existing
        return self.create_memory(
            kind=kind,
            title=title,
            summary=summary,
            metadata=metadata,
            links=normalized_links,
        )

    def record_event(
        self,
        *,
        type: str,
        text: str,
        memory_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timestamp: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        links: Optional[Iterable[MemoryLink | dict[str, Any]]] = None,
    ) -> MemoryEvent:
        normalized_links = self._normalize_links(links or [])
        resolved_memory_id = memory_id or self._resolve_memory_id(normalized_links)
        recorded_at = self._now()

        with self._connect() as conn:
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM events WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    event = self._event_from_row(conn, existing)
                    if resolved_memory_id:
                        self.add_links(
                            resolved_memory_id, normalized_links, event.event_id
                        )
                    return event

            event_id = self._new_id("evt")
            conn.execute(
                """
                INSERT INTO events (
                    event_id, memory_id, idempotency_key, type, timestamp, recorded_at,
                    source, text, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    resolved_memory_id,
                    idempotency_key,
                    type,
                    timestamp,
                    recorded_at,
                    source,
                    text,
                    self._dump_json(metadata or {}),
                ),
            )
            if resolved_memory_id:
                conn.execute(
                    "UPDATE memories SET updated_at = ? WHERE memory_id = ?",
                    (recorded_at, resolved_memory_id),
                )
            for link in normalized_links:
                self._insert_link(conn, resolved_memory_id, event_id, link, recorded_at)
            conn.commit()
            return self._event_from_row(
                conn,
                conn.execute(
                    "SELECT * FROM events WHERE event_id = ?", (event_id,)
                ).fetchone(),
            )

    def add_links(
        self,
        memory_id: str,
        links: Iterable[MemoryLink | dict[str, Any]],
        event_id: Optional[str] = None,
    ) -> None:
        normalized_links = self._normalize_links(links)
        timestamp = self._now()
        with self._connect() as conn:
            for link in normalized_links:
                self._insert_link(conn, memory_id, event_id, link, timestamp)
            conn.execute(
                "UPDATE memories SET updated_at = ? WHERE memory_id = ?",
                (timestamp, memory_id),
            )
            conn.commit()

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        context: str = "memory_search",
    ) -> list[MemorySearchResult]:
        terms = self._tokens(query)
        if not terms:
            logger.info(
                "Memory ranking skipped",
                extra={"context": context, "query": query, "reason": "no_terms"},
            )
            return []

        with self._connect() as conn:
            memory_rows = conn.execute("SELECT * FROM memories").fetchall()
            scores: dict[str, float] = {}
            reasons: dict[str, set[str]] = {}

            for row in memory_rows:
                memory_id = str(row["memory_id"])
                scores[memory_id] = 0.0
                reasons[memory_id] = set()
                self._score_text(
                    scores, reasons, memory_id, terms, row["title"], 15, "title"
                )
                self._score_text(
                    scores, reasons, memory_id, terms, row["summary"], 8, "summary"
                )
                self._score_text(
                    scores,
                    reasons,
                    memory_id,
                    terms,
                    self._dump_json(self._load_json(row["metadata_json"])),
                    5,
                    "metadata",
                )

            for row in conn.execute("SELECT * FROM events").fetchall():
                memory_id = row["memory_id"]
                if not memory_id:
                    continue
                scores.setdefault(memory_id, 0.0)
                reasons.setdefault(memory_id, set())
                self._score_text(
                    scores, reasons, memory_id, terms, row["text"], 10, "event"
                )
                self._score_text(
                    scores,
                    reasons,
                    memory_id,
                    terms,
                    self._dump_json(self._load_json(row["metadata_json"])),
                    8,
                    "event metadata",
                )

            for row in conn.execute("SELECT * FROM links").fetchall():
                memory_id = row["memory_id"]
                if not memory_id:
                    continue
                scores.setdefault(memory_id, 0.0)
                reasons.setdefault(memory_id, set())
                value = str(row["value"] or "")
                matched = terms & self._tokens(value)
                if matched:
                    boost = 50 if row["kind"] == "gmail_thread" else 20
                    scores[memory_id] += len(matched) * boost
                    reasons[memory_id].add(str(row["kind"]))

            ranked_ids = [
                memory_id
                for memory_id, score in sorted(
                    scores.items(), key=lambda item: item[1], reverse=True
                )
                if score > 0
            ][:limit]

            results: list[MemorySearchResult] = []
            for memory_id in ranked_ids:
                row = conn.execute(
                    "SELECT * FROM memories WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
                if row is None:
                    continue
                score = scores[memory_id]
                results.append(
                    MemorySearchResult(
                        memory=self._memory_from_row(conn, row),
                        score=score,
                        confidence=self._confidence(score),
                        reason=self._reason(reasons.get(memory_id, set())),
                    )
                )
            self._log_ranking(
                query=query,
                context=context,
                terms=terms,
                scores=scores,
                reasons=reasons,
                results=results,
                total_memories=len(memory_rows),
            )
            return results

    def render_memory_context(self, memory_id: str, *, event_limit: int = 12) -> str:
        memory = self.get_memory(memory_id)
        if memory is None:
            return ""

        links = (
            "\n".join(f"- {link.kind}: {link.value}" for link in memory.links[:20])
            or "None"
        )
        events = (
            "\n".join(
                f"- [{event.timestamp or event.recorded_at}] {event.type}: {event.text}"
                for event in memory.recent_events[-event_limit:]
            )
            or "None"
        )
        return "\n".join(
            [
                f"Memory ID: {memory.memory_id}",
                f"Kind: {memory.kind}",
                f"Title: {memory.title}",
                f"Summary: {memory.summary or 'None'}",
                "Links:",
                links,
                "Recent Events:",
                events,
            ]
        )

    def clear_all(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM memories")
            conn.commit()

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    memory_id TEXT,
                    idempotency_key TEXT UNIQUE,
                    type TEXT NOT NULL,
                    timestamp TEXT,
                    recorded_at TEXT NOT NULL,
                    source TEXT,
                    text TEXT NOT NULL,
                    metadata_json TEXT,
                    FOREIGN KEY(memory_id) REFERENCES memories(memory_id)
                );

                CREATE TABLE IF NOT EXISTS links (
                    link_id TEXT PRIMARY KEY,
                    memory_id TEXT,
                    event_id TEXT,
                    kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(memory_id) REFERENCES memories(memory_id),
                    FOREIGN KEY(event_id) REFERENCES events(event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_memory_id ON events(memory_id);
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_links_kind_value ON links(kind, value);
                CREATE INDEX IF NOT EXISTS idx_links_memory_id ON links(memory_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency_key
                    ON events(idempotency_key);
                """
            )
            self._dedupe_links(conn)
            conn.execute("DROP INDEX IF EXISTS idx_links_unique")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_links_unique_memory
                    ON links(memory_id, kind, value)
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _memory_from_row(
        self, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> MemoryRecord:
        memory_id = str(row["memory_id"])
        links = [
            MemoryLink(
                kind=str(link["kind"]), value=str(link["value"]), label=link["label"]
            )
            for link in conn.execute(
                "SELECT * FROM links WHERE memory_id = ? ORDER BY created_at DESC",
                (memory_id,),
            ).fetchall()
        ]
        events = [
            self._event_from_row(conn, event)
            for event in conn.execute(
                """
                SELECT * FROM events
                WHERE memory_id = ?
                ORDER BY COALESCE(timestamp, recorded_at) DESC
                LIMIT 12
                """,
                (memory_id,),
            ).fetchall()
        ]
        return MemoryRecord(
            memory_id=memory_id,
            kind=str(row["kind"]),
            title=str(row["title"]),
            summary=str(row["summary"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            metadata=self._load_json(row["metadata_json"]),
            links=links,
            recent_events=list(reversed(events)),
        )

    def _event_from_row(
        self, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> MemoryEvent:
        event_id = str(row["event_id"])
        links = [
            MemoryLink(
                kind=str(link["kind"]), value=str(link["value"]), label=link["label"]
            )
            for link in conn.execute(
                "SELECT * FROM links WHERE event_id = ? ORDER BY created_at DESC",
                (event_id,),
            ).fetchall()
        ]
        return MemoryEvent(
            event_id=event_id,
            memory_id=row["memory_id"],
            idempotency_key=row["idempotency_key"],
            type=str(row["type"]),
            timestamp=row["timestamp"],
            recorded_at=str(row["recorded_at"]),
            source=row["source"],
            text=str(row["text"]),
            metadata=self._load_json(row["metadata_json"]),
            links=links,
        )

    def _insert_link(
        self,
        conn: sqlite3.Connection,
        memory_id: Optional[str],
        event_id: Optional[str],
        link: MemoryLink,
        created_at: str,
    ) -> None:
        if not link.kind or not link.value:
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO links (
                link_id, memory_id, event_id, kind, value, label, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._new_id("lnk"),
                memory_id,
                event_id,
                link.kind,
                link.value,
                link.label,
                created_at,
            ),
        )

    def _dedupe_links(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM links
            WHERE link_id NOT IN (
                SELECT MIN(link_id)
                FROM links
                GROUP BY memory_id, kind, value
            )
            """
        )

    def _resolve_memory_id(self, links: Iterable[MemoryLink]) -> Optional[str]:
        for link in links:
            if link.kind in {"gmail_thread", "gmail_message"}:
                existing = self.find_memory_by_link(kind=link.kind, value=link.value)
                if existing:
                    return existing.memory_id
        return None

    def _normalize_links(
        self, links: Iterable[MemoryLink | dict[str, Any]]
    ) -> list[MemoryLink]:
        normalized: list[MemoryLink] = []
        seen: set[tuple[str, str]] = set()
        for link in links:
            if isinstance(link, MemoryLink):
                candidate = link
            elif isinstance(link, dict):
                candidate = MemoryLink(
                    kind=str(link.get("kind") or "").strip(),
                    value=str(link.get("value") or "").strip(),
                    label=link.get("label"),
                )
            else:
                continue
            key = (candidate.kind, candidate.value)
            if candidate.kind and candidate.value and key not in seen:
                normalized.append(candidate)
                seen.add(key)
        return normalized

    def _score_text(
        self,
        scores: dict[str, float],
        reasons: dict[str, set[str]],
        memory_id: str,
        terms: set[str],
        value: Any,
        weight: float,
        reason: str,
    ) -> None:
        matched = terms & self._tokens(str(value or ""))
        if matched:
            scores[memory_id] += len(matched) * weight
            reasons[memory_id].add(reason)

    def _tokens(self, value: str) -> set[str]:
        return {
            token.lower() for token in _TOKEN_PATTERN.findall(value) if len(token) > 1
        }

    def _reason(self, reasons: set[str]) -> str:
        if not reasons:
            return "lexical memory match"
        return "Matched " + ", ".join(sorted(reasons)[:5])

    def _confidence(self, score: float) -> str:
        if score >= 40:
            return "high"
        if score >= 16:
            return "medium"
        return "low"

    def _log_ranking(
        self,
        *,
        query: str,
        context: str,
        terms: set[str],
        scores: dict[str, float],
        reasons: dict[str, set[str]],
        results: list[MemorySearchResult],
        total_memories: int,
    ) -> None:
        top_candidates = [
            {
                "rank": index,
                "memory_id": result.memory.memory_id,
                "kind": result.memory.kind,
                "title": result.memory.title,
                "score": result.score,
                "confidence": result.confidence,
                "reason": result.reason,
                "updated_at": result.memory.updated_at,
            }
            for index, result in enumerate(results, start=1)
        ]
        scored_count = sum(1 for score in scores.values() if score > 0)
        logger.info(
            "Memory ranking completed",
            extra={
                "context": context,
                "query": query,
                "terms": sorted(terms),
                "total_memories": total_memories,
                "scored_memories": scored_count,
                "returned": len(results),
                "top_candidates": top_candidates,
                "score_reasons": {
                    memory_id: sorted(reason_set)
                    for memory_id, reason_set in reasons.items()
                    if scores.get(memory_id, 0) > 0
                },
            },
        )

    def _dump_json(self, payload: Any) -> str:
        return json.dumps(
            payload or {}, ensure_ascii=False, default=str, sort_keys=True
        )

    def _load_json(self, payload: Any) -> dict[str, Any]:
        if not payload:
            return {}
        try:
            data = json.loads(str(payload))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _now(self) -> str:
        return str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z"))


_memory_store: Optional[MemoryStore] = None
_memory_store_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        with _memory_store_lock:
            if _memory_store is None:
                _memory_store = MemoryStore()
    return _memory_store


__all__ = [
    "MemoryEvent",
    "MemoryLink",
    "MemoryRecord",
    "MemorySearchResult",
    "MemoryStore",
    "get_memory_store",
]
