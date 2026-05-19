"""Pinecone standalone reranking for memory search candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from time import perf_counter
from typing import cast

from ...config import get_settings
from ...logging_config import logger
from .hybrid_search import SearchCandidate

RERANK_MODEL = "bge-reranker-v2-m3"


def rerank_candidates(
    query: str,
    candidates: list[SearchCandidate],
    *,
    limit: int,
) -> list[SearchCandidate]:
    if not candidates:
        return []
    exact = [candidate for candidate in candidates if candidate.exact_priority > 0]
    rerankable = candidates[:100]
    documents = [
        {
            "id": str(index),
            "text": candidate.text or _fallback_text(candidate),
        }
        for index, candidate in enumerate(rerankable)
    ]

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=get_settings().pinecone_api_key)
        started = perf_counter()
        response = pc.inference.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=min(len(documents), limit * 3),
            return_documents=True,
            parameters={"truncate": "END"},
        )
        logger.debug(
            "Pinecone memory rerank completed",
            extra={
                "candidates": len(candidates),
                "rerankable": len(rerankable),
                "returned": min(len(documents), limit * 3),
                "rerank_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
    except Exception as exc:  # pragma: no cover - external service failure
        logger.warning("Pinecone memory rerank failed", extra={"error": str(exc)})
        return candidates[:limit]

    ranked: list[SearchCandidate] = []
    seen: set[tuple[str, str]] = set()
    for row in _rerank_rows(response):
        index = _row_index(row)
        if index is None or index >= len(rerankable):
            continue
        candidate = rerankable[index]
        score = _get(row, "score", 0.0) or 0.0
        candidate.score = max(
            candidate.score,
            float(cast(float | int | str, score)) * 100.0,
        )
        candidate.reason_parts.add("bge rerank")
        ranked.append(candidate)
        seen.add(candidate.dedupe_key)

    for candidate in exact:
        if candidate.dedupe_key not in seen:
            ranked.insert(0, candidate)
            seen.add(candidate.dedupe_key)
    for candidate in candidates:
        if candidate.dedupe_key not in seen:
            ranked.append(candidate)
            seen.add(candidate.dedupe_key)

    return sorted(ranked, key=lambda candidate: candidate.sort_score, reverse=True)[
        :limit
    ]


def _fallback_text(candidate: SearchCandidate) -> str:
    return " ".join(
        str(value)
        for value in [
            candidate.entity_type,
            candidate.memory_id,
            candidate.event_id,
            candidate.metadata.get("text"),
        ]
        if value
    )


def _rerank_rows(response: object) -> list[object]:
    if isinstance(response, Mapping):
        payload = cast(Mapping[object, object], response)
        data: object = payload.get("data") or []
    else:
        data = getattr(response, "data", []) or []
    return list(cast(Iterable[object], data))


def _row_index(row: object) -> int | None:
    index = _get(row, "index")
    if index is not None:
        return int(cast(str | int, index))
    document: object = _get(row, "document", {}) or {}
    doc_id = _get(document, "id")
    return int(cast(str | int, doc_id)) if str(doc_id).isdigit() else None


def _get(value: object, key: str, default: object | None = None) -> object | None:
    if isinstance(value, Mapping):
        payload = cast(Mapping[object, object], value)
        return payload.get(key, default)
    return getattr(value, key, default)
