"""Hybrid memory search over SQLite exact matches and Pinecone candidates."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from os import PathLike
from time import perf_counter
from typing import Protocol, TypeAlias, cast

from ...config import get_settings
from ...logging_config import logger
from .indexer import DENSE_EMBED_MODEL, SPARSE_EMBED_MODEL, pinecone_enabled

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
MEMORY_ID_PATTERN = re.compile(r"\bmem_[a-f0-9]{16,}\b", re.I)
LONG_ID_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]{8,}\b")

SQLitePath: TypeAlias = str | bytes | PathLike[str] | PathLike[bytes]
Metadata: TypeAlias = dict[str, object]
Identifiers: TypeAlias = dict[str, set[str]]
SQLiteParams: TypeAlias = Sequence[object]


class _PineconeEmbedder(Protocol):
    def embed(
        self,
        *,
        model: str,
        inputs: Sequence[str],
        parameters: Mapping[str, str],
    ) -> Sequence[Mapping[str, object]]: ...


class _PineconeIndex(Protocol):
    def query(
        self,
        *,
        namespace: str,
        top_k: int,
        vector: Sequence[float],
        sparse_vector: Mapping[str, Sequence[int] | Sequence[float]],
        include_values: bool,
        include_metadata: bool,
    ) -> object: ...


class _PineconeClient(Protocol):
    inference: _PineconeEmbedder

    def Index(self, *, host: str) -> _PineconeIndex: ...


@dataclass
class SearchCandidate:
    """Raw event or memory candidate before final ranking/packing."""

    entity_type: str
    memory_id: str | None
    event_id: str | None = None
    score: float = 0.0
    exact_priority: int = 0
    sources: set[str] = field(default_factory=set)
    reason_parts: set[str] = field(default_factory=set)
    text: str = ""
    metadata: Metadata = field(default_factory=dict)

    @property
    def dedupe_key(self) -> tuple[str, str]:
        if self.event_id:
            return ("event", self.event_id)
        return ("memory", self.memory_id or "")

    @property
    def sort_score(self) -> float:
        return (self.exact_priority * 1000.0) + self.score


def hybrid_candidates(
    db_path: SQLitePath,
    query: str,
    *,
    top_k: int = 60,
    workspace_id: str,
) -> list[SearchCandidate]:
    candidates: list[SearchCandidate] = []
    with closing(_connect(db_path)) as conn:
        exact = exact_link_candidates(conn, query, workspace_id=workspace_id)
        pinecone = pinecone_candidates(query, top_k=top_k, workspace_id=workspace_id)
        recent = recent_unindexed_candidates(conn, workspace_id=workspace_id)
        candidates.extend(exact)
        candidates.extend(pinecone)
        candidates.extend(recent)
    merged = merge_candidates(candidates)
    _log_hybrid_diagnostics(
        query=query,
        exact=exact,
        pinecone=pinecone,
        recent=recent,
        merged=merged,
    )
    return merged


def exact_link_candidates(
    conn: sqlite3.Connection, query: str, *, workspace_id: str
) -> list[SearchCandidate]:
    identifiers = extract_identifiers(query)
    lowered_query = query.lower()
    candidates: list[SearchCandidate] = []

    for memory_id in identifiers["memory_id"]:
        row = cast(
            sqlite3.Row | None,
            conn.execute(
                """
                SELECT * FROM memories
                WHERE workspace_id = ? AND lower(memory_id) = ?
                """,
                (workspace_id, memory_id.lower()),
            ).fetchone(),
        )
        if row is not None:
            candidates.append(
                SearchCandidate(
                    entity_type="memory",
                    memory_id=_row_text(row, "memory_id"),
                    score=250.0,
                    exact_priority=5,
                    sources={"sqlite_exact"},
                    reason_parts={"exact memory_id"},
                    text=f"{_row_text(row, 'title')} {_row_text(row, 'summary')}",
                )
            )

    link_filters = _exact_link_filters(identifiers)
    if link_filters:
        clauses = " OR ".join("(l.kind = ? AND l.value = ?)" for _ in link_filters)
        params: SQLiteParams = (
            workspace_id,
            *(value for pair in link_filters for value in pair),
        )
        link_rows = cast(
            list[sqlite3.Row],
            conn.execute(
                f"""
                SELECT l.*, e.text AS event_text
                FROM links l
                LEFT JOIN events e ON e.event_id = l.event_id
                WHERE l.workspace_id = ? AND ({clauses})
                """,
                params,
            ).fetchall(),
        )
    else:
        link_rows = []
    for row in link_rows:
        kind = _row_text(row, "kind")
        value = _row_text(row, "value")
        value_lower = value.lower()
        priority = _exact_link_priority(kind, value_lower, identifiers, lowered_query)
        if priority <= 0:
            continue
        candidates.append(
            SearchCandidate(
                entity_type="event" if row["event_id"] else "memory",
                memory_id=_optional_row_text(row, "memory_id"),
                event_id=_optional_row_text(row, "event_id"),
                score=priority * 50.0,
                exact_priority=priority,
                sources={"sqlite_exact"},
                reason_parts={f"exact {kind}"},
                text=_row_text(row, "event_text") or value,
                metadata={"link_kind": kind, "link_value": value},
            )
        )
    return candidates


def pinecone_candidates(
    query: str, *, top_k: int = 60, workspace_id: str
) -> list[SearchCandidate]:
    settings = get_settings()
    if not pinecone_enabled():
        return []

    api_key = settings.pinecone_api_key
    index_host = settings.pinecone_index_host
    if api_key is None or index_host is None:
        return []

    try:
        from pinecone import Pinecone  # type: ignore[import-untyped]

        pinecone_factory = cast(type[_PineconeClient], Pinecone)
        pc = pinecone_factory(api_key=api_key)  # pyright: ignore[reportCallIssue]
        index = pc.Index(host=index_host)
        started = perf_counter()
        dense = pc.inference.embed(
            model=DENSE_EMBED_MODEL,
            inputs=[query],
            parameters={"input_type": "query", "truncate": "END"},
        )[0]
        dense_ms = _elapsed_ms(started)
        started = perf_counter()
        sparse = pc.inference.embed(
            model=SPARSE_EMBED_MODEL,
            inputs=[query],
            parameters={"input_type": "query", "truncate": "END"},
        )[0]
        sparse_ms = _elapsed_ms(started)
        vector = _float_sequence(dense.get("values"))
        sparse_indices = _int_sequence(sparse.get("sparse_indices"))
        sparse_values = _float_sequence(sparse.get("sparse_values"))
        if not vector or not sparse_indices or not sparse_values:
            logger.warning("Pinecone hybrid memory search returned empty vectors")
            return []
        started = perf_counter()
        response = index.query(
            namespace=workspace_id,
            top_k=top_k,
            vector=vector,
            sparse_vector={
                "indices": sparse_indices,
                "values": sparse_values,
            },
            include_values=False,
            include_metadata=True,
        )
        logger.debug(
            "Pinecone hybrid memory search completed",
            extra={
                "top_k": top_k,
                "dense_embed_ms": dense_ms,
                "sparse_embed_ms": sparse_ms,
                "query_ms": _elapsed_ms(started),
            },
        )
    except Exception as exc:  # pragma: no cover - external service failure
        logger.warning(
            "Pinecone hybrid memory search failed", extra={"error": str(exc)}
        )
        return []

    matches = _response_matches(response)
    candidates: list[SearchCandidate] = []
    for match in matches:
        metadata = _metadata_from_match(match)
        entity_type = str(metadata.get("entity_type") or "memory")
        event_id = metadata.get("event_id")
        memory_id = metadata.get("memory_id")
        candidates.append(
            SearchCandidate(
                entity_type=entity_type,
                memory_id=str(memory_id) if memory_id else None,
                event_id=str(event_id) if event_id else None,
                score=_float_value(_get(match, "score", 0.0)),
                sources={"pinecone_hybrid"},
                reason_parts={"hybrid dense+sparse"},
                text=str(metadata.get("text") or ""),
                metadata=metadata,
            )
        )
    return candidates


def recent_unindexed_candidates(
    conn: sqlite3.Connection, *, workspace_id: str, limit: int = 24
) -> list[SearchCandidate]:
    candidates: list[SearchCandidate] = []
    rows = cast(
        list[sqlite3.Row],
        conn.execute(
            """
            SELECT entity_type, entity_id
            FROM memory_index_queue
            WHERE workspace_id = ? AND status IN ('pending', 'failed')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (workspace_id, limit),
        ).fetchall(),
    )
    seen = {
        (_row_text(row, "entity_type"), _row_text(row, "entity_id")) for row in rows
    }

    for entity_type, entity_id in seen:
        if entity_type == "memory":
            row = cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT * FROM memories WHERE workspace_id = ? AND memory_id = ?",
                    (workspace_id, entity_id),
                ).fetchone(),
            )
            if row is not None:
                candidates.append(
                    SearchCandidate(
                        entity_type="memory",
                        memory_id=entity_id,
                        score=5.0,
                        sources={"sqlite_unindexed"},
                        reason_parts={"recent unindexed memory"},
                        text=f"{_row_text(row, 'title')} {_row_text(row, 'summary')}",
                    )
                )
        elif entity_type == "event":
            row = cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT * FROM events WHERE workspace_id = ? AND event_id = ?",
                    (workspace_id, entity_id),
                ).fetchone(),
            )
            if row is not None:
                candidates.append(
                    SearchCandidate(
                        entity_type="event",
                        memory_id=_optional_row_text(row, "memory_id"),
                        event_id=entity_id,
                        score=5.0,
                        sources={"sqlite_unindexed"},
                        reason_parts={"recent unindexed event"},
                        text=_row_text(row, "text"),
                    )
                )

    recent_memory_rows = cast(
        list[sqlite3.Row],
        conn.execute(
            """
            SELECT * FROM memories
            WHERE workspace_id = ?
            ORDER BY updated_at DESC LIMIT 8
            """,
            (workspace_id,),
        ).fetchall(),
    )
    for row in recent_memory_rows:
        candidates.append(
            SearchCandidate(
                entity_type="memory",
                memory_id=_row_text(row, "memory_id"),
                score=1.0,
                sources={"sqlite_recent"},
                reason_parts={"recent memory"},
                text=f"{_row_text(row, 'title')} {_row_text(row, 'summary')}",
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


def extract_identifiers(query: str) -> Identifiers:
    email_matches = cast(list[str], EMAIL_PATTERN.findall(query))
    memory_matches = cast(list[str], MEMORY_ID_PATTERN.findall(query))
    long_matches = cast(list[str], LONG_ID_PATTERN.findall(query))
    emails = {match.lower() for match in email_matches}
    memory_ids = set(memory_matches)
    long_ids = {
        match
        for match in long_matches
        if any(ch.isdigit() for ch in match) and len(match) >= 8
    }
    return {
        "email_address": emails,
        "memory_id": memory_ids,
        "long_id": long_ids,
    }


def _exact_link_filters(identifiers: Identifiers) -> list[tuple[str, str]]:
    filters: set[tuple[str, str]] = set()
    for value in identifiers["email_address"]:
        filters.add(("email_address", value))
    for value in identifiers["long_id"]:
        for kind in ("gmail_thread", "gmail_message", "gmail_draft"):
            filters.add((kind, value))
    return sorted(filters)


def _exact_link_priority(
    kind: str,
    value_lower: str,
    identifiers: Identifiers,
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


def _response_matches(response: object) -> list[object]:
    if isinstance(response, Mapping):
        response_mapping = cast(Mapping[str, object], response)
        matches = response_mapping.get("matches")
    else:
        matches = getattr(response, "matches", None)
    if not isinstance(matches, Sequence) or isinstance(matches, str | bytes):
        return []
    return list(matches)


def _get(value: object, key: str, default: object | None = None) -> object | None:
    if isinstance(value, Mapping):
        value_mapping = cast(Mapping[str, object], value)
        return value_mapping.get(key, default)
    result = getattr(value, key, default)
    return cast(object | None, result)


def _metadata_from_match(match: object) -> Metadata:
    metadata = _get(match, "metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    metadata_mapping = cast(Mapping[object, object], metadata)
    return {str(key): value for key, value in metadata_mapping.items()}


def _float_sequence(value: object | None) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    values: list[float] = []
    for item in value:
        if isinstance(item, int | float):
            values.append(float(item))
    return values


def _int_sequence(value: object | None) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    values: list[int] = []
    for item in value:
        if isinstance(item, int):
            values.append(item)
    return values


def _float_value(value: object | None) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _log_hybrid_diagnostics(
    *,
    query: str,
    exact: list[SearchCandidate],
    pinecone: list[SearchCandidate],
    recent: list[SearchCandidate],
    merged: list[SearchCandidate],
) -> None:
    include_content = get_settings().memory_debug_log_content
    lines = [
        "Hybrid memory candidates",
        (
            f'query_chars="{len(query)}" exact="{len(exact)}" '
            f'pinecone="{len(pinecone)}" recent="{len(recent)}" merged="{len(merged)}"'
        ),
        "<merged_candidates>",
    ]
    for rank, candidate in enumerate(merged[:20], start=1):
        lines.append(
            " ".join(
                [
                    f'rank="{rank}"',
                    f'entity_type="{candidate.entity_type}"',
                    f'memory_id="{candidate.memory_id or ""}"',
                    f'event_id="{candidate.event_id or ""}"',
                    f'score="{candidate.score:.4f}"',
                    f'exact_priority="{candidate.exact_priority}"',
                    f'sources="{",".join(sorted(candidate.sources))}"',
                    f'reasons="{",".join(sorted(candidate.reason_parts))}"',
                ]
            )
        )
        if include_content and candidate.text:
            lines.append(f"text={_truncate(candidate.text, 240)!r}")
        if candidate.metadata:
            metadata = {
                key: value
                for key, value in candidate.metadata.items()
                if key
                in {
                    "entity_type",
                    "memory_id",
                    "event_id",
                    "link_kind",
                    "link_value",
                    "gmail_thread",
                    "gmail_message",
                    "gmail_draft",
                    "email_address",
                }
            }
            if metadata:
                lines.append(f"metadata={metadata!r}")
    lines.append("</merged_candidates>")
    logger.debug("\n".join(lines))


def _truncate(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _row_value(row: sqlite3.Row, key: str) -> object | None:
    return cast(object | None, row[key])


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = _row_value(row, key)
    return str(value) if value is not None else ""


def _optional_row_text(row: sqlite3.Row, key: str) -> str | None:
    text = _row_text(row, key)
    return text or None


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


def _connect(db_path: SQLitePath) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
