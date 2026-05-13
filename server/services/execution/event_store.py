"""Structured execution visibility events for agent runs."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict, cast

from ...logging_config import logger
from ...utils.timezones import now_in_user_timezone

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_EXECUTION_DB_PATH = _DATA_DIR / "execution_events.db"


ExecutionRunStatus = Literal["queued", "running", "completed", "failed"]
ExecutionEventType = Literal["status", "tool-call", "tool-result", "agent-response"]
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
    requestId: str
    memoryId: str
    threadId: str | None
    parentMemoryId: str | None
    title: str
    status: ExecutionRunStatus
    ok: bool | None
    createdAt: str
    updatedAt: str
    parts: list[ExecutionEvent]


class ExecutionEventPayload(TypedDict):
    requestId: str
    memoryId: str
    threadId: str | None
    parentMemoryId: str | None
    title: str
    event: ExecutionEvent


@dataclass
class ExecutionEventSubscription:
    """In-process subscription for live execution events."""

    request_ids: set[str]
    queue: asyncio.Queue[ExecutionEventPayload] = field(default_factory=asyncio.Queue)
    loop: asyncio.AbstractEventLoop = field(default_factory=asyncio.get_running_loop)

    def publish(self, payload: ExecutionEventPayload) -> None:
        request_id = payload["requestId"]
        if request_id not in self.request_ids:
            return
        _ = self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)


class ExecutionEventStore:
    """SQLite-backed run and event store for execution-agent visibility."""

    def __init__(self, db_path: Path = _EXECUTION_DB_PATH) -> None:
        self._db_path: Path = db_path
        self._lock: threading.Lock = threading.Lock()
        self._subscriptions: list[ExecutionEventSubscription] = []
        self._ensure_schema()

    def record_submitted(
        self,
        *,
        request_id: str,
        memory_id: str,
        title: str,
        instructions: str,
        parent_memory_id: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        self._upsert_run(
            request_id=request_id,
            memory_id=memory_id,
            title=title,
            status="queued",
            parent_memory_id=parent_memory_id,
            thread_id=thread_id,
            ok=None,
        )
        self.record_event(
            request_id=request_id,
            memory_id=memory_id,
            parent_memory_id=parent_memory_id,
            thread_id=thread_id,
            event_type="status",
            state="queued",
            text=instructions,
        )

    def record_started(self, *, request_id: str, memory_id: str, title: str) -> None:
        self._upsert_run(
            request_id=request_id,
            memory_id=memory_id,
            title=title,
            status="running",
            ok=None,
        )
        self.record_event(
            request_id=request_id,
            memory_id=memory_id,
            event_type="status",
            state="running",
            text="Execution started",
        )

    def record_tool_call(
        self,
        *,
        request_id: str,
        memory_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_input: JsonValue,
    ) -> None:
        self.record_event(
            request_id=request_id,
            memory_id=memory_id,
            event_type="tool-call",
            state="input-available",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            input_data=tool_input,
        )

    def record_tool_result(
        self,
        *,
        request_id: str,
        memory_id: str,
        tool_call_id: str,
        tool_name: str,
        ok: bool,
        output: JsonValue = None,
        error: str | None = None,
    ) -> None:
        self.record_event(
            request_id=request_id,
            memory_id=memory_id,
            event_type="tool-result",
            state="output-available" if ok else "output-error",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            output=output if ok else None,
            error=error,
        )

    def record_completed(
        self,
        *,
        request_id: str,
        memory_id: str,
        title: str,
        ok: bool,
        response: str,
        error: str | None = None,
    ) -> None:
        status = "completed" if ok else "failed"
        self._upsert_run(
            request_id=request_id,
            memory_id=memory_id,
            title=title,
            status=status,
            ok=ok,
        )
        self.record_event(
            request_id=request_id,
            memory_id=memory_id,
            event_type="agent-response",
            state="output-available" if ok else "output-error",
            text=response,
            error=error,
        )
        self.record_event(
            request_id=request_id,
            memory_id=memory_id,
            event_type="status",
            state=status,
            text=status,
            error=error,
        )

    def record_event(
        self,
        *,
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
        timestamp = self._now()
        event: ExecutionEvent = {
            "id": None,
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
            "requestId": request_id,
            "memoryId": memory_id,
            "threadId": thread_id,
            "parentMemoryId": parent_memory_id,
            "title": memory_id,
            "event": event,
        }
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO execution_events (
                    request_id, memory_id, thread_id, parent_memory_id, type, state,
                    tool_call_id, tool_name, text, input_json, output_json,
                    error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
            _ = conn.execute(
                "UPDATE execution_runs SET updated_at = ? WHERE request_id = ?",
                (timestamp, request_id),
            )
            run = cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT title, thread_id, parent_memory_id FROM execution_runs WHERE request_id = ?",
                    (request_id,),
                ).fetchone(),
            )
            if run is not None:
                title_value = self._row_value(run, "title")
                thread_id_value = self._row_value(run, "thread_id")
                parent_memory_id_value = self._row_value(run, "parent_memory_id")
                payload["title"] = str(title_value)
                payload["threadId"] = payload["threadId"] or self._optional_str(
                    thread_id_value
                )
                payload["parentMemoryId"] = payload[
                    "parentMemoryId"
                ] or self._optional_str(parent_memory_id_value)
            conn.commit()
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            subscription.publish(payload)

    def subscribe(self, request_ids: set[str]) -> ExecutionEventSubscription:
        subscription = ExecutionEventSubscription(request_ids=request_ids)
        with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: ExecutionEventSubscription) -> None:
        with self._lock:
            self._subscriptions = [
                item for item in self._subscriptions if item is not subscription
            ]

    def get_run(self, request_id: str) -> ExecutionRun | None:
        with self._lock, self._connect() as conn:
            row = cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT * FROM execution_runs WHERE request_id = ?",
                    (request_id,),
                ).fetchone(),
            )
            if row is None:
                return None
            events = self._events_by_request(conn, [request_id]).get(request_id, [])
        return {
            "requestId": str(self._row_value(row, "request_id")),
            "memoryId": str(self._row_value(row, "memory_id")),
            "threadId": self._optional_str(self._row_value(row, "thread_id")),
            "parentMemoryId": self._optional_str(
                self._row_value(row, "parent_memory_id")
            ),
            "title": str(self._row_value(row, "title")),
            "status": cast(ExecutionRunStatus, self._row_value(row, "status")),
            "ok": self._optional_bool(self._row_value(row, "ok")),
            "createdAt": str(self._row_value(row, "created_at")),
            "updatedAt": str(self._row_value(row, "updated_at")),
            "parts": events,
        }

    def list_events(
        self, request_id: str, *, after_id: int = 0
    ) -> list[ExecutionEvent]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM execution_events
                WHERE request_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (request_id, max(0, after_id)),
            ).fetchall()
        return [self._event_row_to_part(row) for row in cast(list[sqlite3.Row], rows)]

    def list_runs(
        self, *, limit: int = 30, thread_id: str | None = None
    ) -> list[ExecutionRun]:
        with self._lock, self._connect() as conn:
            if thread_id is None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM execution_runs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(limit, 500)),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM execution_runs
                    WHERE thread_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (thread_id, max(1, min(limit, 500))),
                ).fetchall()
            rows = cast(list[sqlite3.Row], rows)
            request_ids = [str(self._row_value(row, "request_id")) for row in rows]
            events_by_run = self._events_by_request(conn, request_ids)

        return [
            {
                "requestId": str(self._row_value(row, "request_id")),
                "memoryId": str(self._row_value(row, "memory_id")),
                "threadId": self._optional_str(self._row_value(row, "thread_id")),
                "parentMemoryId": self._optional_str(
                    self._row_value(row, "parent_memory_id")
                ),
                "title": str(self._row_value(row, "title")),
                "status": cast(ExecutionRunStatus, self._row_value(row, "status")),
                "ok": self._optional_bool(self._row_value(row, "ok")),
                "createdAt": str(self._row_value(row, "created_at")),
                "updatedAt": str(self._row_value(row, "updated_at")),
                "parts": events_by_run.get(str(self._row_value(row, "request_id")), []),
            }
            for row in rows
        ]

    def clear_all(self) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute("DELETE FROM execution_events")
            _ = conn.execute("DELETE FROM execution_runs")
            conn.commit()

    def _upsert_run(
        self,
        *,
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
                    request_id, memory_id, thread_id, parent_memory_id, title, status,
                    ok, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    memory_id = excluded.memory_id,
                    thread_id = COALESCE(excluded.thread_id, execution_runs.thread_id),
                    parent_memory_id = COALESCE(excluded.parent_memory_id, execution_runs.parent_memory_id),
                    title = excluded.title,
                    status = excluded.status,
                    ok = excluded.ok,
                    updated_at = excluded.updated_at
                """,
                (
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
        request_ids: list[str],
    ) -> dict[str, list[ExecutionEvent]]:
        if not request_ids:
            return {}
        placeholders = ",".join("?" for _ in request_ids)
        rows = conn.execute(
            f"""
            SELECT *
            FROM execution_events
            WHERE request_id IN ({placeholders})
            ORDER BY id ASC
            """,
            request_ids,
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
        return {
            "id": self._optional_int(self._row_value(row, "id")),
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

                CREATE INDEX IF NOT EXISTS idx_execution_events_request
                ON execution_events (request_id, id);

                CREATE INDEX IF NOT EXISTS idx_execution_runs_updated
                ON execution_runs (updated_at);

                """
            )
            self._ensure_column(conn, "execution_runs", "thread_id", "TEXT")
            self._ensure_column(conn, "execution_events", "thread_id", "TEXT")
            _ = conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_runs_thread_updated
                ON execution_runs (thread_id, updated_at)
                """
            )
            conn.commit()

    def _ensure_column(
        self, conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        names = {str(row["name"]) for row in cast(list[sqlite3.Row], rows)}
        if column not in names:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
