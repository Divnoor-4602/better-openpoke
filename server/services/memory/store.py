"""SQLite-backed memory contexts, events, links, and lexical search."""
# pyright: reportUnusedCallResult=false, reportUnnecessaryIsInstance=false

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from ...config import get_settings
from ...core.paths import get_data_dir
from ...core.sqlite_row import SqliteRow
from ...logging_config import logger
from ...utils.timezones import now_in_user_timezone

_DATA_DIR = get_data_dir()
_MEMORY_DB_PATH = _DATA_DIR / "memory.db"
_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")


# `_row` / `_rows` absorb the `Any` that sqlite3's cursor methods return.
# Returning `SqliteRow` (a Protocol that exposes only what sqlite3.Row actually
# implements — __getitem__/keys/__len__/__iter__) keeps the typechecker honest:
# callers can't accidentally invoke .values()/.items()/.get() and crash at
# runtime the way `Mapping[str, object]` allowed.
def _row(value: Any) -> SqliteRow | None:  # pyright: ignore[reportExplicitAny, reportAny]
    """Type the result of sqlite3 fetchone()."""
    if value is None:
        return None
    return cast(SqliteRow, cast(object, value))


def _rows(values: Any) -> list[SqliteRow]:  # pyright: ignore[reportExplicitAny, reportAny]
    """Type the result of sqlite3 fetchall()."""
    return cast("list[SqliteRow]", cast(object, values))


def _opt_str(value: object) -> str | None:
    """Narrow an arbitrary value to str | None for str|None-typed fields."""
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class MemoryLink:
    """A stable external or semantic identifier attached to memory."""

    kind: str
    value: str
    label: str | None = None


@dataclass(frozen=True)
class MemoryEvent:
    """One compact structured event stored in memory."""

    event_id: str
    memory_id: str | None
    idempotency_key: str | None
    type: str
    timestamp: str | None
    recorded_at: str
    source: str | None
    text: str
    metadata: dict[str, object] = field(default_factory=dict)
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
    metadata: dict[str, object] = field(default_factory=dict)
    links: list[MemoryLink] = field(default_factory=list)
    recent_events: list[MemoryEvent] = field(default_factory=list)


@dataclass(frozen=True)
class MemorySearchResult:
    """Ranked memory match returned to prompts and tools."""

    memory: MemoryRecord
    score: float
    confidence: str
    reason: str


from ...core.workspace_context import require_current_workspace


def _resolve_workspace(workspace_id: str | None) -> str:
    return workspace_id or require_current_workspace()



class MemoryStore:
    """Persistence and retrieval for memory contexts."""

    _db_path: Path
    _lock: threading.Lock

    def __init__(self, db_path: Path = _MEMORY_DB_PATH) -> None:
        self._db_path = db_path
        # Used for schema and migration setup; SQLite write conflicts are handled
        # by per-connection transactions and atomic insert paths.
        self._lock = threading.Lock()
        self._ensure_schema()

    def create_memory(
        self,
        *,
        workspace_id: str | None = None,
        kind: str,
        title: str,
        summary: str = "",
        metadata: dict[str, object] | None = None,
        links: Iterable[MemoryLink | dict[str, object]] | None = None,
    ) -> MemoryRecord:
        workspace_id = _resolve_workspace(workspace_id)
        memory_id = self._new_id("mem")
        timestamp = self._now()
        normalized_links = self._normalize_links(links or [])

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    workspace_id, memory_id, kind, title, summary,
                    created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
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
                self._insert_link(
                    conn, workspace_id, memory_id, None, link, timestamp
                )
            self._enqueue_index(
                conn, workspace_id, "memory", memory_id, "upsert", timestamp
            )
            conn.commit()

        memory = self.get_memory(memory_id, workspace_id=workspace_id)
        if memory is None:
            raise RuntimeError(f"Failed to create memory: {memory_id}")
        return memory

    def get_memory(
        self, memory_id: str, *, workspace_id: str | None = None
    ) -> MemoryRecord | None:
        workspace_id = _resolve_workspace(workspace_id)
        with self._connect() as conn:
            row = _row(conn.execute(
                "SELECT * FROM memories WHERE workspace_id = ? AND memory_id = ?",
                (workspace_id, memory_id),
            ).fetchone())
            if row is None:
                return None
            return self._memory_from_row(conn, row)

    def get_memories(
        self, memory_ids: Iterable[str], *, workspace_id: str | None = None
    ) -> dict[str, MemoryRecord]:
        workspace_id = _resolve_workspace(workspace_id)
        ordered_ids = list(
            dict.fromkeys(str(memory_id) for memory_id in memory_ids if memory_id)
        )
        if not ordered_ids:
            return {}
        placeholders = ",".join("?" for _ in ordered_ids)
        with self._connect() as conn:
            rows = _rows(conn.execute(
                f"""
                SELECT * FROM memories
                WHERE workspace_id = ? AND memory_id IN ({placeholders})
                """,
                [workspace_id, *ordered_ids],
            ).fetchall())
            memories = {
                str(row["memory_id"]): self._memory_from_row(conn, row) for row in rows
            }
        return {
            memory_id: memories[memory_id]
            for memory_id in ordered_ids
            if memory_id in memories
        }

    def update_memory(
        self,
        memory_id: str,
        *,
        workspace_id: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> MemoryRecord | None:
        """Update memory display fields without creating a new memory."""
        workspace_id = _resolve_workspace(workspace_id)
        timestamp = self._now()
        with self._connect() as conn:
            existing = _row(conn.execute(
                "SELECT * FROM memories WHERE workspace_id = ? AND memory_id = ?",
                (workspace_id, memory_id),
            ).fetchone())
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
                WHERE workspace_id = ? AND memory_id = ?
                """,
                (
                    title,
                    summary,
                    self._dump_json(existing_metadata),
                    timestamp,
                    workspace_id,
                    memory_id,
                ),
            )
            self._enqueue_index(
                conn, workspace_id, "memory", memory_id, "upsert", timestamp
            )
            conn.commit()
            row = _row(conn.execute(
                "SELECT * FROM memories WHERE workspace_id = ? AND memory_id = ?",
                (workspace_id, memory_id),
            ).fetchone())
            if row is None:
                raise RuntimeError(f"Memory disappeared after update: {memory_id}")
            return self._memory_from_row(conn, row)

    def find_memory_by_link(
        self, *, workspace_id: str | None = None, kind: str, value: str
    ) -> MemoryRecord | None:
        workspace_id = _resolve_workspace(workspace_id)
        normalized_value = str(value).strip()
        if not normalized_value:
            return None
        with self._connect() as conn:
            row = _row(conn.execute(
                """
                SELECT m.*
                FROM memories m
                JOIN links l ON l.memory_id = m.memory_id AND l.workspace_id = m.workspace_id
                WHERE m.workspace_id = ? AND l.kind = ? AND l.value = ?
                ORDER BY m.updated_at DESC
                LIMIT 1
                """,
                (workspace_id, kind, normalized_value),
            ).fetchone())
            if row is None:
                return None
            return self._memory_from_row(conn, row)

    def find_event_by_link(
        self,
        *,
        workspace_id: str | None = None,
        kind: str,
        value: str,
        event_type: str | None = None,
    ) -> MemoryEvent | None:
        """Return the newest event attached to a stable link."""
        workspace_id = _resolve_workspace(workspace_id)
        normalized_value = str(value).strip()
        if not normalized_value:
            return None

        query = """
            SELECT e.*
            FROM events e
            JOIN links l ON l.event_id = e.event_id AND l.workspace_id = e.workspace_id
            WHERE e.workspace_id = ? AND l.kind = ? AND l.value = ?
        """
        params: list[object] = [workspace_id, kind, normalized_value]
        if event_type:
            query += " AND e.type = ?"
            params.append(event_type)
        query += " ORDER BY COALESCE(e.timestamp, e.recorded_at) DESC LIMIT 1"

        with self._connect() as conn:
            row = _row(conn.execute(query, params).fetchone())
            if row is None:
                return None
            return self._event_from_row(conn, row)

    def ensure_memory_for_links(
        self,
        *,
        workspace_id: str | None = None,
        kind: str,
        title: str,
        summary: str = "",
        metadata: dict[str, object] | None = None,
        links: Iterable[MemoryLink | dict[str, object]] | None = None,
    ) -> MemoryRecord:
        workspace_id = _resolve_workspace(workspace_id)
        normalized_links = self._normalize_links(links or [])
        for link in normalized_links:
            if link.kind in {"gmail_thread", "gmail_message"}:
                existing = self.find_memory_by_link(
                    workspace_id=workspace_id, kind=link.kind, value=link.value
                )
                if existing is not None:
                    self.add_links(
                        existing.memory_id,
                        normalized_links,
                        workspace_id=workspace_id,
                    )
                    return existing
        return self.create_memory(
            workspace_id=workspace_id,
            kind=kind,
            title=title,
            summary=summary,
            metadata=metadata,
            links=normalized_links,
        )

    def record_event(
        self,
        *,
        workspace_id: str | None = None,
        type: str,
        text: str,
        memory_id: str | None = None,
        idempotency_key: str | None = None,
        timestamp: str | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        links: Iterable[MemoryLink | dict[str, object]] | None = None,
    ) -> MemoryEvent:
        workspace_id = _resolve_workspace(workspace_id)
        normalized_links = self._normalize_links(links or [])
        resolved_memory_id = memory_id or self._resolve_memory_id(
            workspace_id, normalized_links
        )
        recorded_at = self._now()

        with self._connect() as conn:
            event_id = self._new_id("evt")
            insert_verb = "INSERT OR IGNORE" if idempotency_key else "INSERT"
            try:
                conn.execute(
                    f"""
                    {insert_verb} INTO events (
                        workspace_id, event_id, memory_id, idempotency_key, type,
                        timestamp, recorded_at, source, text, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_id,
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
            except sqlite3.IntegrityError:
                if not idempotency_key:
                    raise

            if idempotency_key:
                row = _row(conn.execute(
                    """
                    SELECT * FROM events
                    WHERE workspace_id = ? AND idempotency_key = ?
                    """,
                    (workspace_id, idempotency_key),
                ).fetchone())
                if row is None:
                    raise sqlite3.IntegrityError(
                        f"Failed to resolve event for idempotency_key={idempotency_key}"
                    )
                if str(row["event_id"]) != event_id:
                    event = self._event_from_row(conn, row)
                    if resolved_memory_id:
                        for link in normalized_links:
                            self._insert_link(
                                conn,
                                workspace_id,
                                resolved_memory_id,
                                event.event_id,
                                link,
                                recorded_at,
                            )
                        conn.execute(
                            """
                            UPDATE memories SET updated_at = ?
                            WHERE workspace_id = ? AND memory_id = ?
                            """,
                            (recorded_at, workspace_id, resolved_memory_id),
                        )
                        self._enqueue_index(
                            conn, workspace_id, "memory",
                            resolved_memory_id, "upsert", recorded_at,
                        )
                        self._enqueue_index(
                            conn, workspace_id, "event",
                            event.event_id, "upsert", recorded_at,
                        )
                        conn.commit()
                    return event

            if resolved_memory_id:
                conn.execute(
                    """
                    UPDATE memories SET updated_at = ?
                    WHERE workspace_id = ? AND memory_id = ?
                    """,
                    (recorded_at, workspace_id, resolved_memory_id),
                )
                self._enqueue_index(
                    conn, workspace_id, "memory",
                    resolved_memory_id, "upsert", recorded_at,
                )
            for link in normalized_links:
                self._insert_link(
                    conn, workspace_id, resolved_memory_id,
                    event_id, link, recorded_at,
                )
            self._enqueue_index(
                conn, workspace_id, "event", event_id, "upsert", recorded_at
            )
            conn.commit()
            final_row = _row(conn.execute(
                "SELECT * FROM events WHERE workspace_id = ? AND event_id = ?",
                (workspace_id, event_id),
            ).fetchone())
            if final_row is None:
                raise RuntimeError(f"Event disappeared after insert: {event_id}")
            return self._event_from_row(conn, final_row)

    def add_links(
        self,
        memory_id: str,
        links: Iterable[MemoryLink | dict[str, object]],
        event_id: str | None = None,
        *,
        workspace_id: str | None = None,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        normalized_links = self._normalize_links(links)
        timestamp = self._now()
        with self._connect() as conn:
            for link in normalized_links:
                self._insert_link(
                    conn, workspace_id, memory_id, event_id, link, timestamp
                )
            conn.execute(
                """
                UPDATE memories SET updated_at = ?
                WHERE workspace_id = ? AND memory_id = ?
                """,
                (timestamp, workspace_id, memory_id),
            )
            self._enqueue_index(
                conn, workspace_id, "memory", memory_id, "upsert", timestamp
            )
            if event_id:
                self._enqueue_index(
                    conn, workspace_id, "event", event_id, "upsert", timestamp
                )
            conn.commit()

    def search(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 8,
        context: str = "memory_search",
    ) -> list[MemorySearchResult]:
        workspace_id = _resolve_workspace(workspace_id)
        from .hybrid_search import hybrid_candidates
        from .indexer import pinecone_enabled
        from .ranking import PromptContextRanker, SearchResultRanker
        from .rerank import rerank_candidates

        if pinecone_enabled():
            started = perf_counter()
            try:
                candidates = hybrid_candidates(
                    self._db_path, query, top_k=60, workspace_id=workspace_id
                )
                if candidates:
                    ranked_candidates = rerank_candidates(
                        query,
                        candidates,
                        limit=max(limit, 1),
                    )
                    ranker = (
                        PromptContextRanker(self, workspace_id=workspace_id)
                        if context == "prompt_context"
                        else SearchResultRanker(self, workspace_id=workspace_id)
                    )
                    results = cast(
                        list[MemorySearchResult],
                        ranker.rank(ranked_candidates, limit=limit),
                    )
                    if results:
                        self._log_ranked_results(
                            context=context,
                            results=results,
                            backend="pinecone_hybrid",
                        )
                        logger.debug(
                            "Hybrid memory ranking completed",
                            extra={
                                "context": context,
                                "query_length": len(query),
                                "returned": len(results),
                                "backend": "pinecone_hybrid",
                                "elapsed_ms": round(
                                    (perf_counter() - started) * 1000, 2
                                ),
                                "reranked": any(
                                    "bge rerank" in result.reason for result in results
                                ),
                                "matches": [
                                    {
                                        "rank": rank,
                                        "memory_id": result.memory.memory_id,
                                        "title": result.memory.title,
                                        "score": round(result.score, 3),
                                        "confidence": result.confidence,
                                        "reason": result.reason,
                                        "matched_events": self._log_events(
                                            result.memory.recent_events[:3]
                                        ),
                                    }
                                    for rank, result in enumerate(results, start=1)
                                ],
                            },
                        )
                        return results
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning(
                    "Hybrid memory search unavailable; falling back to lexical search",
                    extra={"context": context, "error": str(exc)},
                )

        return self._search_lexical(
            query, workspace_id=workspace_id, limit=limit, context=context
        )

    def _log_ranked_results(
        self,
        *,
        context: str,
        results: list[MemorySearchResult],
        backend: str,
    ) -> None:
        include_content = get_settings().memory_debug_log_content
        lines = [
            "Ranked memory results",
            f'context="{context}" backend="{backend}" returned="{len(results)}"',
            "<ranked_memories>",
        ]
        for rank, result in enumerate(results, start=1):
            memory = result.memory
            lines.append(
                " ".join(
                    [
                        f'rank="{rank}"',
                        f'memory_id="{memory.memory_id}"',
                        f'kind="{memory.kind}"',
                        f'score="{result.score:.4f}"',
                        f'confidence="{result.confidence}"',
                        f'reason="{result.reason}"',
                        f'title="{self._truncate_log_text(memory.title, 120)}"',
                    ]
                )
            )
            if include_content:
                lines.append(
                    f"summary={self._truncate_log_text(memory.summary, 240)!r}"
                )
            if memory.links:
                links = [
                    f"{link.kind}:{self._truncate_log_text(link.value, 80)}"
                    for link in memory.links[:12]
                ]
                lines.append(f"links={links!r}")
            lines.append("<events>")
            for event in memory.recent_events[:8]:
                event_line = (
                    f'event_id="{event.event_id}" type="{event.type}" '
                    f'timestamp="{event.timestamp or event.recorded_at}"'
                )
                if include_content:
                    event_line += f" text={self._truncate_log_text(event.text, 240)!r}"
                lines.append(event_line)
            lines.append("</events>")
        lines.append("</ranked_memories>")
        logger.debug("\n".join(lines))

    def _search_lexical(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 8,
        context: str = "memory_search",
    ) -> list[MemorySearchResult]:
        workspace_id = _resolve_workspace(workspace_id)
        terms = self._tokens(query)
        if not terms:
            logger.debug(
                "Memory ranking skipped",
                extra={"context": context, "query": query, "reason": "no_terms"},
            )
            return []

        with self._connect() as conn:
            memory_rows = _rows(conn.execute(
                """
                SELECT * FROM memories
                WHERE workspace_id = ?
                ORDER BY updated_at DESC LIMIT 1000
                """,
                (workspace_id,),
            ).fetchall())
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

            for row in _rows(conn.execute(
                """
                SELECT * FROM events
                WHERE workspace_id = ?
                ORDER BY COALESCE(timestamp, recorded_at) DESC
                LIMIT 5000
                """,
                (workspace_id,),
            ).fetchall()):
                memory_id_value = _opt_str(row["memory_id"])
                if not memory_id_value:
                    continue
                memory_id = memory_id_value
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

            for row in _rows(conn.execute(
                """
                SELECT * FROM links
                WHERE workspace_id = ?
                ORDER BY created_at DESC LIMIT 5000
                """,
                (workspace_id,),
            ).fetchall()):
                memory_id_value = _opt_str(row["memory_id"])
                if not memory_id_value:
                    continue
                memory_id = memory_id_value
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
                row = _row(conn.execute(
                    "SELECT * FROM memories WHERE workspace_id = ? AND memory_id = ?",
                    (workspace_id, memory_id),
                ).fetchone())
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

    def render_memory_context(
        self,
        memory_id: str,
        *,
        workspace_id: str | None = None,
        query: str | None = None,
        event_limit: int = 12,
    ) -> str:
        workspace_id = _resolve_workspace(workspace_id)
        memory = self.get_memory(memory_id, workspace_id=workspace_id)
        if memory is None:
            return ""

        links = (
            "\n".join(f"- {link.kind}: {link.value}" for link in memory.links[:20])
            or "None"
        )
        selected_events = self._rank_memory_events(memory, query, event_limit)
        events = (
            "\n".join(
                f"- [{event.timestamp or event.recorded_at}] {event.type}: {event.text}"
                for event in selected_events
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

    def _rank_memory_events(
        self,
        memory: MemoryRecord,
        query: str | None,
        event_limit: int,
    ) -> list[MemoryEvent]:
        if not query:
            return memory.recent_events[-event_limit:]
        terms = self._tokens(query)
        if not terms:
            return memory.recent_events[-event_limit:]
        scored: list[tuple[float, int, MemoryEvent]] = []
        for index, event in enumerate(memory.recent_events):
            score = len(terms & self._tokens(event.text)) * 10
            score += len(terms & self._tokens(self._dump_json(event.metadata))) * 5
            scored.append((float(score), index, event))
        relevant = [item for item in scored if item[0] > 0]
        latest = scored[-min(3, len(scored)) :]
        merged: dict[str, tuple[float, int, MemoryEvent]] = {
            item[2].event_id: item
            for item in sorted(relevant, key=lambda item: item[0], reverse=True)[
                :event_limit
            ]
        }
        for item in latest:
            merged.setdefault(item[2].event_id, item)
        selected = sorted(
            merged.values(),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )[:event_limit]
        return [item[2] for item in sorted(selected, key=lambda item: item[1])]

    def clear_all(self) -> None:
        """Dev-only: wipe every workspace's memory. Used by dev reset routes."""
        with self._connect() as conn:
            timestamp = self._now()
            for row in _rows(conn.execute(
                "SELECT workspace_id, memory_id FROM memories"
            ).fetchall()):
                self._enqueue_index(
                    conn,
                    str(row["workspace_id"]),
                    "memory",
                    str(row["memory_id"]),
                    "delete",
                    timestamp,
                )
            for row in _rows(conn.execute(
                "SELECT workspace_id, event_id FROM events"
            ).fetchall()):
                self._enqueue_index(
                    conn,
                    str(row["workspace_id"]),
                    "event",
                    str(row["event_id"]),
                    "delete",
                    timestamp,
                )
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM memories")
            conn.commit()

    def clear_workspace(self, workspace_id: str) -> None:
        with self._connect() as conn:
            timestamp = self._now()
            for row in _rows(conn.execute(
                "SELECT memory_id FROM memories WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchall()):
                self._enqueue_index(
                    conn,
                    workspace_id,
                    "memory",
                    str(row["memory_id"]),
                    "delete",
                    timestamp,
                )
            for row in _rows(conn.execute(
                "SELECT event_id FROM events WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchall()):
                self._enqueue_index(
                    conn,
                    workspace_id,
                    "event",
                    str(row["event_id"]),
                    "delete",
                    timestamp,
                )
            conn.execute(
                "DELETE FROM links WHERE workspace_id = ?", (workspace_id,)
            )
            conn.execute(
                "DELETE FROM events WHERE workspace_id = ?", (workspace_id,)
            )
            conn.execute(
                "DELETE FROM memories WHERE workspace_id = ?", (workspace_id,)
            )
            conn.commit()

    def list_workspaces(self) -> list[str]:
        with self._connect() as conn:
            rows = _rows(conn.execute(
                "SELECT DISTINCT workspace_id FROM memories"
            ).fetchall())
        return [str(row["workspace_id"]) for row in rows]

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    workspace_id TEXT NOT NULL,
                    memory_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    workspace_id TEXT NOT NULL,
                    event_id TEXT PRIMARY KEY,
                    memory_id TEXT,
                    idempotency_key TEXT,
                    type TEXT NOT NULL,
                    timestamp TEXT,
                    recorded_at TEXT NOT NULL,
                    source TEXT,
                    text TEXT NOT NULL,
                    metadata_json TEXT,
                    FOREIGN KEY(memory_id) REFERENCES memories(memory_id)
                );

                CREATE TABLE IF NOT EXISTS links (
                    workspace_id TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS memory_index_queue (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    available_at TEXT,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_workspace
                    ON memories(workspace_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_workspace_memory
                    ON events(workspace_id, memory_id);
                CREATE INDEX IF NOT EXISTS idx_events_workspace_type
                    ON events(workspace_id, type);
                CREATE INDEX IF NOT EXISTS idx_events_workspace_timestamp
                    ON events(workspace_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_links_workspace_kind_value
                    ON links(workspace_id, kind, value);
                CREATE INDEX IF NOT EXISTS idx_links_workspace_memory
                    ON links(workspace_id, memory_id);
                CREATE INDEX IF NOT EXISTS idx_memory_index_queue_status
                    ON memory_index_queue(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_memory_index_queue_workspace_entity
                    ON memory_index_queue(workspace_id, entity_type, entity_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_workspace_idempotency
                    ON events(workspace_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_links_unique_workspace_memory
                    ON links(workspace_id, memory_id, kind, value);
                CREATE INDEX IF NOT EXISTS idx_memory_index_queue_status_available
                    ON memory_index_queue(status, available_at, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_index_queue_active_idempotency
                    ON memory_index_queue(workspace_id, idempotency_key)
                    WHERE status IN ('pending', 'failed', 'processing')
                      AND idempotency_key IS NOT NULL;
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _memory_from_row(
        self, conn: sqlite3.Connection, row: SqliteRow
    ) -> MemoryRecord:
        memory_id = str(row["memory_id"])
        workspace_id = str(row["workspace_id"])
        links = [
            MemoryLink(
                kind=str(link["kind"]),
                value=str(link["value"]),
                label=_opt_str(link["label"]),
            )
            for link in _rows(
                conn.execute(
                    """
                    SELECT * FROM links
                    WHERE workspace_id = ? AND memory_id = ?
                    ORDER BY created_at DESC
                    """,
                    (workspace_id, memory_id),
                ).fetchall()
            )
        ]
        events = [
            self._event_from_row(conn, event)
            for event in _rows(
                conn.execute(
                    """
                    SELECT * FROM events
                    WHERE workspace_id = ? AND memory_id = ?
                    ORDER BY COALESCE(timestamp, recorded_at) DESC
                    LIMIT 12
                    """,
                    (workspace_id, memory_id),
                ).fetchall()
            )
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
        self, conn: sqlite3.Connection, row: SqliteRow
    ) -> MemoryEvent:
        event_id = str(row["event_id"])
        workspace_id = str(row["workspace_id"])
        links = [
            MemoryLink(
                kind=str(link["kind"]),
                value=str(link["value"]),
                label=_opt_str(link["label"]),
            )
            for link in _rows(
                conn.execute(
                    """
                    SELECT * FROM links
                    WHERE workspace_id = ? AND event_id = ?
                    ORDER BY created_at DESC
                    """,
                    (workspace_id, event_id),
                ).fetchall()
            )
        ]
        return MemoryEvent(
            event_id=event_id,
            memory_id=_opt_str(row["memory_id"]),
            idempotency_key=_opt_str(row["idempotency_key"]),
            type=str(row["type"]),
            timestamp=_opt_str(row["timestamp"]),
            recorded_at=str(row["recorded_at"]),
            source=_opt_str(row["source"]),
            text=str(row["text"]),
            metadata=self._load_json(row["metadata_json"]),
            links=links,
        )

    def _insert_link(
        self,
        conn: sqlite3.Connection,
        workspace_id: str,
        memory_id: str | None,
        event_id: str | None,
        link: MemoryLink,
        created_at: str,
    ) -> None:
        if not link.kind or not link.value:
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO links (
                workspace_id, link_id, memory_id, event_id, kind, value, label, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                self._new_id("lnk"),
                memory_id,
                event_id,
                link.kind,
                link.value,
                link.label,
                created_at,
            ),
        )

    def _enqueue_index(
        self,
        conn: sqlite3.Connection,
        workspace_id: str,
        entity_type: str,
        entity_id: str | None,
        operation: str,
        version: str,
    ) -> None:
        if not entity_id:
            return

        timestamp = self._now()
        idempotency_key = f"{workspace_id}:{operation}:{entity_type}:{entity_id}"
        queue_id = self._new_id("idx")
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_index_queue (
                    id, workspace_id, idempotency_key, entity_type, entity_id,
                    operation, version, status, attempts, available_at,
                    max_attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                """,
                (
                    queue_id,
                    workspace_id,
                    idempotency_key,
                    entity_type,
                    entity_id,
                    operation,
                    version,
                    timestamp,
                    get_settings().memory_index_max_attempts,
                    timestamp,
                    timestamp,
                ),
            )
        except sqlite3.IntegrityError:
            pass

        existing = _row(conn.execute(
            """
            SELECT id FROM memory_index_queue
            WHERE workspace_id = ? AND idempotency_key = ?
              AND status IN ('pending', 'failed', 'processing')
            LIMIT 1
            """,
            (workspace_id, idempotency_key),
        ).fetchone())
        if existing is not None:
            conn.execute(
                """
                UPDATE memory_index_queue
                SET version = ?,
                    status = 'pending',
                    attempts = 0,
                    last_error = NULL,
                    available_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (version, timestamp, timestamp, str(existing["id"])),
            )
            return

    def _ensure_queue_columns_unused(self, conn: sqlite3.Connection) -> None:  # noqa: ARG002 - kept for legacy reference
        columns = {
            str(row["name"])
            for row in _rows(conn.execute("PRAGMA table_info(memory_index_queue)").fetchall())
        }
        if "idempotency_key" not in columns:
            conn.execute(
                "ALTER TABLE memory_index_queue ADD COLUMN idempotency_key TEXT"
            )
        if "available_at" not in columns:
            conn.execute("ALTER TABLE memory_index_queue ADD COLUMN available_at TEXT")
        if "max_attempts" not in columns:
            conn.execute(
                "ALTER TABLE memory_index_queue ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5"
            )
        self._dedupe_index_queue(conn)
        conn.execute(
            """
            UPDATE memory_index_queue
            SET idempotency_key = operation || ':' || entity_type || ':' || entity_id
            WHERE idempotency_key IS NULL
            """
        )
        conn.execute(
            """
            UPDATE memory_index_queue
            SET available_at = COALESCE(available_at, updated_at, created_at)
            WHERE status IN ('pending', 'failed', 'processing')
              AND available_at IS NULL
            """
        )
        conn.execute(
            """
            UPDATE memory_index_queue
            SET max_attempts = ?
            WHERE max_attempts IS NULL OR max_attempts <= 0
            """,
            (get_settings().memory_index_max_attempts,),
        )

    def _dedupe_index_queue(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM memory_index_queue
            WHERE status IN ('pending', 'failed', 'processing')
              AND rowid NOT IN (
                  SELECT MAX(rowid)
                  FROM memory_index_queue
                  WHERE status IN ('pending', 'failed', 'processing')
                  GROUP BY COALESCE(
                      idempotency_key,
                      operation || ':' || entity_type || ':' || entity_id
                  )
              )
            """
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

    def _resolve_memory_id(
        self, workspace_id: str, links: Iterable[MemoryLink]
    ) -> str | None:
        for link in links:
            if link.kind in {"gmail_thread", "gmail_message"}:
                existing = self.find_memory_by_link(
                    workspace_id=workspace_id, kind=link.kind, value=link.value
                )
                if existing:
                    return existing.memory_id
        return None

    def _normalize_links(
        self, links: Iterable[MemoryLink | dict[str, object]]
    ) -> list[MemoryLink]:
        normalized: list[MemoryLink] = []
        seen: set[tuple[str, str]] = set()
        for link in links:
            if isinstance(link, MemoryLink):
                candidate = link
            elif isinstance(link, dict):
                label_value = link.get("label")
                candidate = MemoryLink(
                    kind=str(link.get("kind") or "").strip(),
                    value=str(link.get("value") or "").strip(),
                    label=label_value if isinstance(label_value, str) else None,
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
        value: object,
        weight: float,
        reason: str,
    ) -> None:
        matched = terms & self._tokens(str(value or ""))
        if matched:
            scores[memory_id] += len(matched) * weight
            reasons[memory_id].add(reason)

    def _tokens(self, value: str) -> set[str]:
        # `re.Pattern.findall` returns `list[Any]` in typeshed because its shape
        # depends on whether the pattern has groups. This pattern has none, so
        # the result is `list[str]`.
        tokens = cast(list[str], _TOKEN_PATTERN.findall(value))
        return {token.lower() for token in tokens if len(token) > 1}

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

    def _truncate_log_text(self, value: str, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _log_events(self, events: list[MemoryEvent]) -> list[dict[str, str]]:
        include_content = get_settings().memory_debug_log_content
        logged: list[dict[str, str]] = []
        for event in events:
            payload = {"event_id": event.event_id, "type": event.type}
            if include_content:
                payload["text"] = self._truncate_log_text(event.text, 180)
            logged.append(payload)
        return logged

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
        logger.debug(
            "Memory ranking completed",
            extra={
                "context": context,
                "query_length": len(query),
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

    def _dump_json(self, payload: object) -> str:
        return json.dumps(
            payload or {}, ensure_ascii=False, default=str, sort_keys=True
        )

    def _load_json(self, payload: object) -> dict[str, object]:
        if not payload:
            return {}
        try:
            data = cast(object, json.loads(str(payload)))
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return cast(dict[str, object], data)
        return {}

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _now(self) -> str:
        return str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z"))


_memory_store: MemoryStore | None = None
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
