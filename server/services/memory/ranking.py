"""Final packing of hybrid search candidates into MemorySearchResult objects."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from importlib import import_module
from typing import Protocol, cast

from ...core.sqlite_row import SqliteRow
from .hybrid_search import SearchCandidate


class _MemoryEvent(Protocol):
    @property
    def event_id(self) -> str: ...


class _MemoryRecord(Protocol):
    @property
    def memory_id(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def summary(self) -> str: ...

    @property
    def created_at(self) -> str: ...

    @property
    def updated_at(self) -> str: ...

    @property
    def metadata(self) -> Mapping[str, object]: ...

    @property
    def links(self) -> Sequence[object]: ...

    @property
    def recent_events(self) -> Sequence[_MemoryEvent]: ...


class _MemorySearchResult(Protocol):
    @property
    def memory(self) -> _MemoryRecord: ...

    @property
    def score(self) -> float: ...

    @property
    def confidence(self) -> str: ...

    @property
    def reason(self) -> str: ...


class _MemoryStore(Protocol):
    def get_memories(
        self, memory_ids: Iterable[str], *, workspace_id: str | None = None
    ) -> Mapping[str, _MemoryRecord]: ...

    def _connect(self) -> sqlite3.Connection: ...

    def _event_from_row(
        self, conn: sqlite3.Connection, row: SqliteRow
    ) -> _MemoryEvent: ...


class _MemorySearchResultFactory(Protocol):
    def __call__(
        self,
        *,
        memory: _MemoryRecord,
        score: float,
        confidence: str,
        reason: str,
    ) -> _MemorySearchResult: ...


class _MemoryRecordFactory(Protocol):
    def __call__(
        self,
        *,
        memory_id: str,
        kind: str,
        title: str,
        summary: str,
        created_at: str,
        updated_at: str,
        metadata: Mapping[str, object],
        links: Sequence[object],
        recent_events: Sequence[_MemoryEvent],
    ) -> _MemoryRecord: ...


class PromptContextRanker:
    """Group event-level hits by memory for prompt context packing."""

    def __init__(
        self, store: _MemoryStore, *, workspace_id: str | None = None
    ) -> None:
        self._store: _MemoryStore = store
        self._workspace_id: str | None = workspace_id

    def rank(
        self,
        candidates: list[SearchCandidate],
        *,
        limit: int,
    ) -> list[_MemorySearchResult]:
        grouped: dict[str, SearchCandidate] = {}
        for candidate in candidates:
            if not candidate.memory_id:
                continue
            existing = grouped.get(candidate.memory_id)
            if existing is None or candidate.sort_score > existing.sort_score:
                grouped[candidate.memory_id] = candidate
            else:
                existing.reason_parts.update(candidate.reason_parts)
                existing.sources.update(candidate.sources)

        return _results_from_candidates(
            self._store,
            sorted(grouped.values(), key=lambda item: item.sort_score, reverse=True),
            limit=limit,
            workspace_id=self._workspace_id,
        )


class SearchResultRanker:
    """Preserve event-level matches while returning memory-compatible results."""

    def __init__(
        self, store: _MemoryStore, *, workspace_id: str | None = None
    ) -> None:
        self._store: _MemoryStore = store
        self._workspace_id: str | None = workspace_id

    def rank(
        self,
        candidates: list[SearchCandidate],
        *,
        limit: int,
    ) -> list[_MemorySearchResult]:
        return _results_from_candidates(
            self._store,
            candidates,
            limit=limit,
            workspace_id=self._workspace_id,
        )


def _results_from_candidates(
    store: _MemoryStore,
    candidates: list[SearchCandidate],
    *,
    limit: int,
    workspace_id: str | None = None,
) -> list[_MemorySearchResult]:
    MemorySearchResult = cast(
        _MemorySearchResultFactory,
        import_module("server.services.memory.store").MemorySearchResult,
    )

    results: list[_MemorySearchResult] = []
    seen_memory_ids: set[str] = set()
    candidate_memory_ids: list[str] = []
    for candidate in candidates:
        if candidate.memory_id and candidate.memory_id not in candidate_memory_ids:
            candidate_memory_ids.append(candidate.memory_id)
        if len(candidate_memory_ids) >= max(limit * 3, limit):
            break
    memories = store.get_memories(candidate_memory_ids, workspace_id=workspace_id)
    for candidate in candidates:
        memory_id = candidate.memory_id
        if not memory_id or memory_id in seen_memory_ids:
            continue
        memory = memories.get(memory_id)
        if memory is None:
            continue
        if candidate.event_id:
            memory = _memory_with_matched_event_first(
                store, memory, candidate.event_id, workspace_id=workspace_id
            )
        results.append(
            MemorySearchResult(
                memory=memory,
                score=candidate.sort_score,
                confidence=_confidence(candidate.sort_score),
                reason=_reason(candidate),
            )
        )
        seen_memory_ids.add(memory_id)
        if len(results) >= limit:
            break
    return results


def _memory_with_matched_event_first(
    store: _MemoryStore,
    memory: _MemoryRecord,
    event_id: str,
    *,
    workspace_id: str | None = None,
) -> _MemoryRecord:
    MemoryRecord = cast(
        _MemoryRecordFactory,
        import_module("server.services.memory.store").MemoryRecord,
    )

    with store._connect() as conn:  # pyright: ignore[reportPrivateUsage]
        if workspace_id is not None:
            row = cast(
                "SqliteRow | None",
                conn.execute(
                    "SELECT * FROM events WHERE workspace_id = ? AND event_id = ?",
                    (workspace_id, event_id),
                ).fetchone(),
            )
        else:
            row = cast(
                "SqliteRow | None",
                conn.execute(
                    "SELECT * FROM events WHERE event_id = ?",
                    (event_id,),
                ).fetchone(),
            )
        if row is None:
            return memory
        event = store._event_from_row(  # pyright: ignore[reportPrivateUsage]
            conn, row
        )
    events = [
        event,
        *[
            existing
            for existing in memory.recent_events
            if existing.event_id != event_id
        ],
    ]
    return MemoryRecord(
        memory_id=memory.memory_id,
        kind=memory.kind,
        title=memory.title,
        summary=memory.summary,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        metadata=memory.metadata,
        links=memory.links,
        recent_events=events[:12],
    )


def _reason(candidate: SearchCandidate) -> str:
    reasons = sorted(candidate.reason_parts)
    sources = sorted(candidate.sources)
    if reasons:
        return "Matched " + ", ".join(reasons[:5])
    if sources:
        return "Matched " + ", ".join(sources[:5])
    return "hybrid memory match"


def _confidence(score: float) -> str:
    if score >= 100:
        return "high"
    if score >= 20:
        return "medium"
    return "low"
