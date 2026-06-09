from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ...core.sqlite_row import SqliteRow
from ...logging_config import logger
from .models import TriggerRecord
from .utils import to_storage_timestamp, utc_now


def _row(value: Any) -> SqliteRow | None:  # pyright: ignore[reportExplicitAny, reportAny]
    if value is None:
        return None
    return cast(SqliteRow, cast(object, value))


def _rows(values: Any) -> list[SqliteRow]:  # pyright: ignore[reportExplicitAny, reportAny]
    return cast("list[SqliteRow]", cast(object, values))

_TriggerFieldValue = str | None
_INSERTABLE_TRIGGER_FIELDS = {
    "workspace_id",
    "agent_name",
    "payload",
    "start_time",
    "next_trigger",
    "recurrence_rule",
    "timezone",
    "status",
    "last_error",
    "created_at",
    "updated_at",
}
_UPDATABLE_TRIGGER_FIELDS = _INSERTABLE_TRIGGER_FIELDS - {
    "workspace_id",
    "agent_name",
    "created_at",
}


from ...core.workspace_context import require_current_workspace


def _resolve_workspace(workspace_id: str | None) -> str:
    return workspace_id or require_current_workspace()



class TriggerStore:
    """Low-level persistence for triggers backed by SQLite, scoped by workspace."""

    _db_path: Path
    _lock: threading.Lock

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_directory()
        self._ensure_schema()

    def _ensure_directory(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "trigger directory creation failed",
                extra={"error": str(exc)},
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute("PRAGMA journal_mode=WAL;")
            _ = conn.execute(
                """
                CREATE TABLE IF NOT EXISTS triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    start_time TEXT,
                    next_trigger TEXT,
                    recurrence_rule TEXT,
                    timezone TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            _ = conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_triggers_workspace_agent_next
                ON triggers (workspace_id, agent_name, next_trigger);
                """
            )
            _ = conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_triggers_status_next
                ON triggers (status, next_trigger);
                """
            )

    def insert(self, payload: Mapping[str, _TriggerFieldValue]) -> int:
        self._validate_fields(payload, _INSERTABLE_TRIGGER_FIELDS)
        if "workspace_id" not in payload:
            raise ValueError("workspace_id is required when inserting a trigger")
        with self._lock, self._connect() as conn:
            columns = ", ".join(payload.keys())
            placeholders = ", ".join([":" + key for key in payload.keys()])
            sql = f"INSERT INTO triggers ({columns}) VALUES ({placeholders})"
            cursor = conn.execute(sql, payload)
            trigger_id = cursor.lastrowid
            if trigger_id is None:  # pragma: no cover - defensive
                raise RuntimeError("INSERT did not return a row id")
            return int(trigger_id)

    def fetch_one(
        self, trigger_id: int, agent_name: str, *, workspace_id: str | None = None
    ) -> TriggerRecord | None:
        workspace_id = _resolve_workspace(workspace_id)
        with self._lock, self._connect() as conn:
            row = _row(conn.execute(
                """
                SELECT * FROM triggers
                WHERE id = ? AND agent_name = ? AND workspace_id = ?
                """,
                (trigger_id, agent_name, workspace_id),
            ).fetchone())
        return self._row_to_record(row) if row else None

    def update(
        self,
        trigger_id: int,
        agent_name: str,
        fields: Mapping[str, _TriggerFieldValue],
        *,
        workspace_id: str | None = None,
    ) -> bool:
        workspace_id = _resolve_workspace(workspace_id)
        if not fields:
            return False
        self._validate_fields(fields, _UPDATABLE_TRIGGER_FIELDS)
        assignments = ", ".join(f"{key} = :{key}" for key in fields.keys())
        sql = (
            f"UPDATE triggers SET {assignments}, updated_at = :updated_at"
            " WHERE id = :trigger_id AND agent_name = :agent_name"
            " AND workspace_id = :workspace_id"
        )
        payload: dict[str, object] = {
            **fields,
            "updated_at": to_storage_timestamp(utc_now()),
            "trigger_id": trigger_id,
            "agent_name": agent_name,
            "workspace_id": workspace_id,
        }
        with self._lock, self._connect() as conn:
            cursor = conn.execute(sql, payload)
            return cursor.rowcount > 0

    def _validate_fields(self, fields: Mapping[str, object], allowed: set[str]) -> None:
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(
                f"Unsupported trigger field(s): {', '.join(sorted(invalid))}"
            )

    def list_for_agent(
        self, agent_name: str, *, workspace_id: str | None = None
    ) -> list[TriggerRecord]:
        workspace_id = _resolve_workspace(workspace_id)
        with self._lock, self._connect() as conn:
            rows = _rows(conn.execute(
                """
                SELECT * FROM triggers
                WHERE agent_name = ? AND workspace_id = ?
                ORDER BY next_trigger IS NULL, next_trigger
                """,
                (agent_name, workspace_id),
            ).fetchall())
        return [self._row_to_record(row) for row in rows]

    def fetch_due(
        self,
        agent_name: str | None,
        before_iso: str,
        *,
        workspace_id: str | None = None,
    ) -> list[TriggerRecord]:
        """Fetch due triggers.

        When workspace_id is None, returns due triggers across ALL
        workspaces (used by the scheduler so it can dispatch each one
        to the right workspace). When given, scopes to that workspace.
        Intentionally does NOT resolve from the ContextVar — the
        cross-workspace contract must survive being called from a
        background loop that hasn't bound one.
        """
        sql = (
            "SELECT * FROM triggers WHERE status = 'active'"
            " AND next_trigger IS NOT NULL AND next_trigger <= ?"
        )
        params: list[str] = [before_iso]
        if agent_name is not None:
            sql += " AND agent_name = ?"
            params.append(agent_name)
        if workspace_id is not None:
            sql += " AND workspace_id = ?"
            params.append(workspace_id)
        sql += " ORDER BY next_trigger, id"
        with self._lock, self._connect() as conn:
            rows = _rows(conn.execute(sql, params).fetchall())
        return [self._row_to_record(row) for row in rows]

    def list_workspaces(self) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = _rows(conn.execute(
                "SELECT DISTINCT workspace_id FROM triggers"
            ).fetchall())
        return [str(row["workspace_id"]) for row in rows]

    def clear_all(self) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute("DELETE FROM triggers")

    def clear_workspace(self, workspace_id: str) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute(
                "DELETE FROM triggers WHERE workspace_id = ?",
                (workspace_id,),
            )

    def _row_to_record(self, row: SqliteRow) -> TriggerRecord:
        data: dict[str, object] = {key: row[key] for key in row.keys()}
        return TriggerRecord.model_validate(data)


__all__ = ["TriggerStore"]
