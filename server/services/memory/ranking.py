"""Final packing of hybrid search candidates into MemorySearchResult objects."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .hybrid_search import SearchCandidate


class PromptContextRanker:
    """Group event-level hits by memory for prompt context packing."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def rank(
        self,
        candidates: list[SearchCandidate],
        *,
        limit: int,
    ) -> list[Any]:
        grouped: dict[str, SearchCandidate] = {}
        for candidate in candidates:
            if not candidate.memory_id:
                continue
            existing = grouped.get(candidate.memory_id)
            if existing is None or candidate.sort_score > existing.sort_score:
                grouped[candidate.memory_id] = candidate
            elif existing is not None:
                existing.reason_parts.update(candidate.reason_parts)
                existing.sources.update(candidate.sources)

        return _results_from_candidates(
            self._store,
            sorted(grouped.values(), key=lambda item: item.sort_score, reverse=True),
            limit=limit,
        )


class SearchResultRanker:
    """Preserve event-level matches while returning memory-compatible results."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def rank(
        self,
        candidates: list[SearchCandidate],
        *,
        limit: int,
    ) -> list[Any]:
        return _results_from_candidates(self._store, candidates, limit=limit)


def _results_from_candidates(
    store: Any,
    candidates: list[SearchCandidate],
    *,
    limit: int,
) -> list[Any]:
    MemorySearchResult = import_module("server.services.memory.store").MemorySearchResult

    results: list[Any] = []
    seen_memory_ids: set[str] = set()
    for candidate in candidates:
        memory_id = candidate.memory_id
        if not memory_id or memory_id in seen_memory_ids:
            continue
        memory = store.get_memory(memory_id)
        if memory is None:
            continue
        if candidate.event_id:
            memory = _memory_with_matched_event_first(store, memory, candidate.event_id)
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
    store: Any,
    memory: Any,
    event_id: str,
) -> Any:
    MemoryRecord = import_module("server.services.memory.store").MemoryRecord

    with store._connect() as conn:
        row = conn.execute(
            "SELECT * FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return memory
        event = store._event_from_row(conn, row)
    events = [event] + [existing for existing in memory.recent_events if existing.event_id != event_id]
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
