"""Structured execution visibility events for agent runs."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Literal, TypeAlias, TypedDict, cast

from ...core.paths import get_data_dir
from ...core.workspace_context import require_current_workspace
from ...logging_config import logger
from ...utils.timezones import now_in_user_timezone


def _resolve_workspace(workspace_id: str | None) -> str:
    return workspace_id or require_current_workspace()

_DATA_DIR = get_data_dir()
_EXECUTION_DB_PATH = _DATA_DIR / "execution_events.db"


ExecutionRunStatus = Literal["queued", "running", "completed", "failed"]
LifecycleScope = Literal["interaction", "execution"]
ExecutionEventType = Literal[
    "run.created",
    "run.started",
    "model.started",
    "model.text.delta",
    "model.reasoning.delta",
    "model.completed",
    "tool.input.started",
    "tool.input.delta",
    "tool.input.available",
    "tool.output.available",
    "tool.output.error",
    "execution.submitted",
    "message.created",
    "run.completed",
    "run.failed",
    "error",
    "status",
    "tool-call",
    "tool-result",
    "agent-response",
]
ExecutionEventState = Literal[
    "queued",
    "running",
    "input-available",
    "output-available",
    "output-error",
    "completed",
    "failed",
]
JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
SQLiteValue: TypeAlias = str | int | float | bytes | None


class ExecutionEvent(TypedDict):
    id: int | None
    runId: str
    sequence: int
    type: ExecutionEventType
    state: ExecutionEventState | None
    toolCallId: str | None
    toolName: str | None
    text: str | None
    input: JsonValue
    output: JsonValue
    error: str | None
    createdAt: str


class ExecutionRun(TypedDict):
    runId: str
    requestId: str
    memoryId: str
    threadId: str | None
    parentMemoryId: str | None
    parentRunId: str | None
    scope: LifecycleScope
    title: str
    status: ExecutionRunStatus
    ok: bool | None
    createdAt: str
    updatedAt: str
    parts: list[ExecutionEvent]


class ExecutionEventPayload(TypedDict):
    workspaceId: str
    runId: str
    requestId: str
    memoryId: str
    threadId: str | None
    parentMemoryId: str | None
    parentRunId: str | None
    scope: LifecycleScope
    title: str
    event: ExecutionEvent


# Cap each subscription's in-memory queue. A slow client backing up behind
# 512 unread events is almost certainly broken or gone — at which point we
# prefer to lose the oldest waiting events rather than grow the queue
# unboundedly and OOM the server. The store's index is the source of truth
# anyway; a reconnect can backfill from SQLite.
_SUBSCRIPTION_QUEUE_MAXSIZE: int = 512


@dataclass
class ExecutionEventSubscription:
    """In-process subscription for live execution events.

    Subscriptions are workspace-scoped: a sub only ever receives events
    matching its `workspace_id`. The store's indexes are keyed by
    (workspace_id, …) so live fan-out never crosses workspaces even if
    two testers happen to share a thread_id or request_id by accident.
    """

    workspace_id: str
    request_ids: set[str]
    thread_id: str | None = None
    queue: asyncio.Queue[ExecutionEventPayload] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_SUBSCRIPTION_QUEUE_MAXSIZE)
    )
    loop: asyncio.AbstractEventLoop = field(default_factory=asyncio.get_running_loop)

    def publish(self, payload: ExecutionEventPayload) -> None:
        """Enqueue an already-matched payload. Filtering is handled by the
        store before this is called — see `ExecutionEventStore.record_event`.
        """
        _ = self.loop.call_soon_threadsafe(self._safe_enqueue, payload)

    def _safe_enqueue(self, payload: ExecutionEventPayload) -> None:
        try:
            self.queue.put_nowait(payload)
            return
        except asyncio.QueueFull:
            pass
        try:
            _ = self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.debug(
                "subscription queue full after eviction; dropping payload",
                extra={
                    "workspace_id": payload.get("workspaceId"),
                    "request_id": payload.get("requestId"),
                    "thread_id": payload.get("threadId"),
                },
            )


class ExecutionEventStore:
    """SQLite-backed run and event store for execution-agent visibility.

    Live subscriptions are indexed by (workspace_id, criterion) so
    publish-time fan-out is O(1 + matching subs) AND never crosses
    workspaces.
    """

    def __init__(self, db_path: Path = _EXECUTION_DB_PATH) -> None:
        self._db_path: Path = db_path
        self._lock: threading.Lock = threading.Lock()
        # Indexes keyed by (workspace_id, filter_value).
        self._thread_index: dict[tuple[str, str], list[ExecutionEventSubscription]] = {}
        self._request_index: dict[tuple[str, str], list[ExecutionEventSubscription]] = {}
        # Wildcard / compound subs are still per-workspace.
        self._wildcard_subs: dict[str, list[ExecutionEventSubscription]] = {}
        self._compound_subs: dict[str, list[ExecutionEventSubscription]] = {}
        self._ensure_schema()

    def record_submitted(
        self,
        *,
        workspace_id: str | None = None,
        request_id: str,
        memory_id: str,
        title: str,
        instructions: str,
        parent_memory_id: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        self._upsert_run(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            title=title,
            status="queued",
            parent_memory_id=parent_memory_id,
            thread_id=thread_id,
            ok=None,
        )
        self.record_event(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            parent_memory_id=parent_memory_id,
            thread_id=thread_id,
            event_type="execution.submitted",
            state="queued",
            text=instructions,
        )

    def record_started(
        self,
        *,
        workspace_id: str | None = None,
        request_id: str,
        memory_id: str,
        title: str,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        self._upsert_run(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            title=title,
            status="running",
            ok=None,
        )
        self.record_event(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            event_type="run.started",
            state="running",
            text="Execution started",
        )

    def record_tool_call(
        self,
        *,
        workspace_id: str | None = None,
        request_id: str,
        memory_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_input: JsonValue,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        self.record_event(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            event_type="tool.input.available",
            state="input-available",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            input_data=tool_input,
        )

    def record_tool_result(
        self,
        *,
        workspace_id: str | None = None,
        request_id: str,
        memory_id: str,
        tool_call_id: str,
        tool_name: str,
        ok: bool,
        output: JsonValue = None,
        error: str | None = None,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        self.record_event(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            event_type="tool.output.available" if ok else "tool.output.error",
            state="output-available" if ok else "output-error",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            output=output if ok else None,
            error=error,
        )

    def record_completed(
        self,
        *,
        workspace_id: str | None = None,
        request_id: str,
        memory_id: str,
        title: str,
        ok: bool,
        response: str,
        error: str | None = None,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        status = "completed" if ok else "failed"
        self._upsert_run(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            title=title,
            status=status,
            ok=ok,
        )
        self.record_event(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            event_type="message.created",
            state="output-available" if ok else "output-error",
            text=response,
            error=error,
        )
        self.record_event(
            workspace_id=workspace_id,
            request_id=request_id,
            memory_id=memory_id,
            event_type="run.completed" if ok else "run.failed",
            state=status,
            text=status,
            error=error,
        )

    def record_event(
        self,
        *,
        workspace_id: str | None = None,
        request_id: str,
        memory_id: str,
        event_type: ExecutionEventType,
        state: ExecutionEventState | None = None,
        parent_memory_id: str | None = None,
        thread_id: str | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        text: str | None = None,
        input_data: JsonValue = None,
        output: JsonValue = None,
        error: str | None = None,
    ) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        timestamp = self._now()
        sequence = self._next_sequence(workspace_id, request_id)
        event: ExecutionEvent = {
            "id": None,
            "runId": request_id,
            "sequence": sequence,
            "type": event_type,
            "state": state,
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "text": text,
            "input": input_data,
            "output": output,
            "error": error,
            "createdAt": timestamp,
        }
        payload: ExecutionEventPayload = {
            "workspaceId": workspace_id,
            "runId": request_id,
            "requestId": request_id,
            "memoryId": memory_id,
            "threadId": thread_id,
            "parentMemoryId": parent_memory_id,
            "parentRunId": parent_memory_id,
            "scope": "execution",
            "title": memory_id,
            "event": event,
        }
        with self._lock, self._connect() as conn:
            run = cast(
                sqlite3.Row | None,
                conn.execute(
                    """
                    SELECT title, thread_id, parent_memory_id
                    FROM execution_runs
                    WHERE workspace_id = ? AND request_id = ?
                    """,
                    (workspace_id, request_id),
                ).fetchone(),
            )
            if run is not None:
                title_value = self._row_value(run, "title")
                thread_id_value = self._row_value(run, "thread_id")
                parent_memory_id_value = self._row_value(run, "parent_memory_id")
                payload["title"] = str(title_value)
                thread_id = thread_id or self._optional_str(thread_id_value)
                parent_memory_id = parent_memory_id or self._optional_str(
                    parent_memory_id_value
                )
                payload["threadId"] = thread_id
                payload["parentMemoryId"] = parent_memory_id
            cursor = conn.execute(
                """
                INSERT INTO execution_events (
                    workspace_id, request_id, memory_id, thread_id, parent_memory_id,
                    type, state, tool_call_id, tool_name, text, input_json, output_json,
                    error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    request_id,
                    memory_id,
                    thread_id,
                    parent_memory_id,
                    event_type,
                    state,
                    tool_call_id,
                    tool_name,
                    text,
                    self._dump_json(input_data),
                    self._dump_json(output),
                    error,
                    timestamp,
                ),
            )
            event["id"] = cursor.lastrowid
            event["sequence"] = self._optional_int(cursor.lastrowid) or sequence
            _ = conn.execute(
                """
                UPDATE execution_runs
                SET updated_at = ?
                WHERE workspace_id = ? AND request_id = ?
                """,
                (timestamp, workspace_id, request_id),
            )
            conn.commit()
            targets = self._collect_targets_locked(payload)
        for subscription in targets:
            subscription.publish(payload)

    def _collect_targets_locked(
        self, payload: ExecutionEventPayload
    ) -> list[ExecutionEventSubscription]:
        """Return the subscriptions that should receive `payload`. Caller
        must hold `self._lock`. Order is stable: thread → request →
        wildcard → compound. All lookups are scoped to the payload's
        workspace_id, so live events never cross workspaces.
        """
        targets: list[ExecutionEventSubscription] = []
        seen: set[int] = set()
        workspace_id = payload["workspaceId"]
        thread_id = payload.get("threadId")
        if isinstance(thread_id, str):
            for sub in self._thread_index.get((workspace_id, thread_id), ()):
                if id(sub) not in seen:
                    seen.add(id(sub))
                    targets.append(sub)
        request_id = payload["requestId"]
        for sub in self._request_index.get((workspace_id, request_id), ()):
            if id(sub) not in seen:
                seen.add(id(sub))
                targets.append(sub)
        for sub in self._wildcard_subs.get(workspace_id, ()):
            if id(sub) not in seen:
                seen.add(id(sub))
                targets.append(sub)
        for sub in self._compound_subs.get(workspace_id, ()):
            if id(sub) in seen:
                continue
            matched_thread = (
                sub.thread_id is not None
                and isinstance(thread_id, str)
                and thread_id == sub.thread_id
            )
            matched_request = (
                bool(sub.request_ids) and request_id in sub.request_ids
            )
            if matched_thread or matched_request:
                seen.add(id(sub))
                targets.append(sub)
        return targets

    def subscribe(
        self,
        *,
        workspace_id: str | None = None,
        request_ids: set[str] | None = None,
        thread_id: str | None = None,
    ) -> ExecutionEventSubscription:
        """Create a workspace-scoped subscription.

        The store indexes it by (workspace_id, criterion) so publishes
        only walk subs from the same workspace.
        """
        workspace_id = _resolve_workspace(workspace_id)
        normalized_request_ids: set[str] = set(request_ids or ())
        subscription = ExecutionEventSubscription(
            workspace_id=workspace_id,
            request_ids=normalized_request_ids,
            thread_id=thread_id,
        )
        has_thread = thread_id is not None
        has_requests = bool(normalized_request_ids)
        with self._lock:
            if has_thread and has_requests:
                self._compound_subs.setdefault(workspace_id, []).append(subscription)
            elif has_thread:
                assert thread_id is not None
                self._thread_index.setdefault(
                    (workspace_id, thread_id), []
                ).append(subscription)
            elif has_requests:
                for rid in normalized_request_ids:
                    self._request_index.setdefault(
                        (workspace_id, rid), []
                    ).append(subscription)
            else:
                self._wildcard_subs.setdefault(workspace_id, []).append(subscription)
        return subscription

    def unsubscribe(self, subscription: ExecutionEventSubscription) -> None:
        workspace_id = subscription.workspace_id
        with self._lock:
            bucket = self._wildcard_subs.get(workspace_id)
            if bucket is not None:
                remaining = [item for item in bucket if item is not subscription]
                if remaining:
                    self._wildcard_subs[workspace_id] = remaining
                else:
                    _ = self._wildcard_subs.pop(workspace_id, None)
            bucket = self._compound_subs.get(workspace_id)
            if bucket is not None:
                remaining = [item for item in bucket if item is not subscription]
                if remaining:
                    self._compound_subs[workspace_id] = remaining
                else:
                    _ = self._compound_subs.pop(workspace_id, None)
            if subscription.thread_id is not None:
                key = (workspace_id, subscription.thread_id)
                bucket = self._thread_index.get(key)
                if bucket is not None:
                    remaining = [item for item in bucket if item is not subscription]
                    if remaining:
                        self._thread_index[key] = remaining
                    else:
                        _ = self._thread_index.pop(key, None)
            for rid in subscription.request_ids:
                key = (workspace_id, rid)
                bucket = self._request_index.get(key)
                if bucket is None:
                    continue
                remaining = [item for item in bucket if item is not subscription]
                if remaining:
                    self._request_index[key] = remaining
                else:
                    _ = self._request_index.pop(key, None)

    def get_run(
        self, request_id: str, *, workspace_id: str | None = None
    ) -> ExecutionRun | None:
        workspace_id = _resolve_workspace(workspace_id)
        with self._lock, self._connect() as conn:
            row = cast(
                sqlite3.Row | None,
                conn.execute(
                    """
                    SELECT * FROM execution_runs
                    WHERE workspace_id = ? AND request_id = ?
                    """,
                    (workspace_id, request_id),
                ).fetchone(),
            )
            if row is None:
                return None
            events = self._events_by_request(
                conn, workspace_id, [request_id]
            ).get(request_id, [])
        return {
            "runId": str(self._row_value(row, "request_id")),
            "requestId": str(self._row_value(row, "request_id")),
            "memoryId": str(self._row_value(row, "memory_id")),
            "threadId": self._optional_str(self._row_value(row, "thread_id")),
            "parentMemoryId": self._optional_str(
                self._row_value(row, "parent_memory_id")
            ),
            "parentRunId": self._optional_str(self._row_value(row, "parent_memory_id")),
            "scope": "execution",
            "title": str(self._row_value(row, "title")),
            "status": cast(ExecutionRunStatus, self._row_value(row, "status")),
            "ok": self._optional_bool(self._row_value(row, "ok")),
            "createdAt": str(self._row_value(row, "created_at")),
            "updatedAt": str(self._row_value(row, "updated_at")),
            "parts": events,
        }

    def list_events(
        self,
        request_id: str,
        *,
        workspace_id: str | None = None,
        after_id: int = 0,
    ) -> list[ExecutionEvent]:
        workspace_id = _resolve_workspace(workspace_id)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM execution_events
                WHERE workspace_id = ? AND request_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (workspace_id, request_id, max(0, after_id)),
            ).fetchall()
        return [self._event_row_to_part(row) for row in cast(list[sqlite3.Row], rows)]

    def list_runs(
        self,
        *,
        workspace_id: str | None = None,
        limit: int = 30,
        offset: int = 0,
        thread_id: str | None = None,
    ) -> list[ExecutionRun]:
        workspace_id = _resolve_workspace(workspace_id)
        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        with self._lock, self._connect() as conn:
            if thread_id is None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM execution_runs
                    WHERE workspace_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (workspace_id, safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM execution_runs
                    WHERE workspace_id = ? AND thread_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (workspace_id, thread_id, safe_limit, safe_offset),
                ).fetchall()
            rows = cast(list[sqlite3.Row], rows)
            request_ids = [str(self._row_value(row, "request_id")) for row in rows]
            events_by_run = self._events_by_request(conn, workspace_id, request_ids)

        return [
            {
                "requestId": str(self._row_value(row, "request_id")),
                "runId": str(self._row_value(row, "request_id")),
                "memoryId": str(self._row_value(row, "memory_id")),
                "threadId": self._optional_str(self._row_value(row, "thread_id")),
                "parentMemoryId": self._optional_str(
                    self._row_value(row, "parent_memory_id")
                ),
                "parentRunId": self._optional_str(
                    self._row_value(row, "parent_memory_id")
                ),
                "scope": "execution",
                "title": str(self._row_value(row, "title")),
                "status": cast(ExecutionRunStatus, self._row_value(row, "status")),
                "ok": self._optional_bool(self._row_value(row, "ok")),
                "createdAt": str(self._row_value(row, "created_at")),
                "updatedAt": str(self._row_value(row, "updated_at")),
                "parts": events_by_run.get(str(self._row_value(row, "request_id")), []),
            }
            for row in rows
        ]

    def list_workspaces(self) -> list[str]:
        """Return every workspace that has ever recorded a run.

        Background workers use this to fan out across all workspaces
        instead of running as a single global loop.
        """
        with self._lock, self._connect() as conn:
            rows = cast(
                "list[Mapping[str, object]]",
                cast(object, conn.execute(
                    "SELECT DISTINCT workspace_id FROM execution_runs"
                ).fetchall()),
            )
        return [str(row["workspace_id"]) for row in rows]

    def clear_all(self) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute("DELETE FROM execution_events")
            _ = conn.execute("DELETE FROM execution_runs")
            conn.commit()

    def clear_workspace(self, workspace_id: str) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute(
                "DELETE FROM execution_events WHERE workspace_id = ?",
                (workspace_id,),
            )
            _ = conn.execute(
                "DELETE FROM execution_runs WHERE workspace_id = ?",
                (workspace_id,),
            )
            conn.commit()

    def _upsert_run(
        self,
        *,
        workspace_id: str,
        request_id: str,
        memory_id: str,
        title: str,
        status: ExecutionRunStatus,
        ok: bool | None,
        parent_memory_id: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        timestamp = self._now()
        with self._lock, self._connect() as conn:
            _ = conn.execute(
                """
                INSERT INTO execution_runs (
                    workspace_id, request_id, memory_id, thread_id, parent_memory_id,
                    title, status, ok, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    memory_id = excluded.memory_id,
                    thread_id = COALESCE(excluded.thread_id, execution_runs.thread_id),
                    parent_memory_id = COALESCE(excluded.parent_memory_id, execution_runs.parent_memory_id),
                    title = excluded.title,
                    status = excluded.status,
                    ok = excluded.ok,
                    updated_at = excluded.updated_at
                WHERE execution_runs.workspace_id = excluded.workspace_id
                """,
                (
                    workspace_id,
                    request_id,
                    memory_id,
                    thread_id,
                    parent_memory_id,
                    title,
                    status,
                    None if ok is None else int(ok),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()

    def _events_by_request(
        self,
        conn: sqlite3.Connection,
        workspace_id: str,
        request_ids: list[str],
    ) -> dict[str, list[ExecutionEvent]]:
        if not request_ids:
            return {}
        placeholders = ",".join("?" for _ in request_ids)
        rows = conn.execute(
            f"""
            SELECT *
            FROM execution_events
            WHERE workspace_id = ? AND request_id IN ({placeholders})
            ORDER BY id ASC
            """,
            [workspace_id, *request_ids],
        ).fetchall()
        grouped: dict[str, list[ExecutionEvent]] = {
            request_id: [] for request_id in request_ids
        }
        for row in cast(list[sqlite3.Row], rows):
            grouped.setdefault(str(self._row_value(row, "request_id")), []).append(
                self._event_row_to_part(row)
            )
        return grouped

    def _event_row_to_part(self, row: sqlite3.Row) -> ExecutionEvent:
        event_id = self._optional_int(self._row_value(row, "id"))
        return {
            "id": event_id,
            "runId": str(self._row_value(row, "request_id")),
            "sequence": event_id or 0,
            "type": cast(ExecutionEventType, self._row_value(row, "type")),
            "state": cast(
                ExecutionEventState | None,
                self._optional_str(self._row_value(row, "state")),
            ),
            "toolCallId": self._optional_str(self._row_value(row, "tool_call_id")),
            "toolName": self._optional_str(self._row_value(row, "tool_name")),
            "text": self._optional_str(self._row_value(row, "text")),
            "input": self._load_json(self._row_value(row, "input_json")),
            "output": self._load_json(self._row_value(row, "output_json")),
            "error": self._optional_str(self._row_value(row, "error")),
            "createdAt": str(self._row_value(row, "created_at")),
        }

    def _ensure_schema(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "execution event directory creation failed", extra={"error": str(exc)}
            )
        with self._connect() as conn:
            _ = conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_runs (
                    workspace_id TEXT NOT NULL,
                    request_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    thread_id TEXT,
                    parent_memory_id TEXT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ok INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    thread_id TEXT,
                    parent_memory_id TEXT,
                    type TEXT NOT NULL,
                    state TEXT,
                    tool_call_id TEXT,
                    tool_name TEXT,
                    text TEXT,
                    input_json TEXT,
                    output_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_execution_events_workspace_request
                ON execution_events (workspace_id, request_id, id);

                CREATE INDEX IF NOT EXISTS idx_execution_runs_workspace_updated
                ON execution_runs (workspace_id, updated_at);

                CREATE INDEX IF NOT EXISTS idx_execution_runs_workspace_thread_updated
                ON execution_runs (workspace_id, thread_id, updated_at);
                """
            )
            conn.commit()

    def _next_sequence(self, workspace_id: str, request_id: str) -> int:
        with self._connect() as conn:
            raw = cast(object, conn.execute(
                """
                SELECT COALESCE(MAX(id), 0) + 1 AS sequence
                FROM execution_events
                WHERE workspace_id = ? AND request_id = ?
                """,
                (workspace_id, request_id),
            ).fetchone())
        if raw is None:
            return 1
        row = cast(Mapping[str, object], raw)
        return int(cast(int, row["sequence"]))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _dump_json(self, payload: JsonValue) -> str | None:
        if payload is None:
            return None
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            return json.dumps(str(payload), ensure_ascii=False)

    def _load_json(self, payload: SQLiteValue) -> JsonValue:
        if payload is None:
            return None
        try:
            return cast(JsonValue, json.loads(str(payload)))
        except json.JSONDecodeError:
            return str(payload)

    def _row_value(self, row: sqlite3.Row, key: str) -> SQLiteValue:
        return cast(SQLiteValue, row[key])

    def _optional_str(self, value: SQLiteValue) -> str | None:
        if value is None:
            return None
        return str(value)

    def _optional_int(self, value: SQLiteValue) -> int | None:
        if value is None:
            return None
        return int(value)

    def _optional_bool(self, value: SQLiteValue) -> bool | None:
        if value is None:
            return None
        return bool(value)

    def _now(self) -> str:
        return str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z"))


_execution_event_store = ExecutionEventStore(_EXECUTION_DB_PATH)


def get_execution_event_store() -> ExecutionEventStore:
    return _execution_event_store


__all__ = ["ExecutionEventStore", "get_execution_event_store"]
