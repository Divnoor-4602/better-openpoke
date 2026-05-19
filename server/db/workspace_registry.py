"""Workspace registry: tracks when each handle was first seen and from which IP.

Observability only — doesn't reject anything. When a second IP shows up for an
already-registered handle, we log a warning so demo operators can spot
collisions on the same shared password. Stored in its own SQLite file
(`workspace_registry.db`) so it stays out of the per-workspace data DBs.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, cast

from ..core.paths import get_data_dir
from ..core.sqlite_row import SqliteRow
from ..logging_config import logger
from ..utils.timezones import now_in_user_timezone

_DATA_DIR = get_data_dir()
_REGISTRY_DB_PATH = _DATA_DIR / "workspace_registry.db"


def _row(value: Any) -> SqliteRow | None:  # pyright: ignore[reportExplicitAny, reportAny]
    if value is None:
        return None
    return cast(SqliteRow, cast(object, value))


def _rows(values: Any) -> list[SqliteRow]:  # pyright: ignore[reportExplicitAny, reportAny]
    return cast("list[SqliteRow]", cast(object, values))


class WorkspaceRegistry:
    """First-seen-wins registry for demo workspaces."""

    _db_path: Path
    _lock: threading.Lock

    def __init__(self, db_path: Path = _REGISTRY_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def register(self, workspace_id: str, request_ip: str | None) -> None:
        """Record this workspace + IP. Log a warning if the IP changed."""
        timestamp = self._now()
        with self._lock, self._connect() as conn:
            existing = _row(conn.execute(
                "SELECT first_seen_at, first_ip FROM workspace_registry WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone())
            if existing is None:
                _ = conn.execute(
                    """
                    INSERT INTO workspace_registry
                        (workspace_id, first_seen_at, first_ip)
                    VALUES (?, ?, ?)
                    """,
                    (workspace_id, timestamp, request_ip),
                )
                conn.commit()
                logger.info(
                    "workspace registered",
                    extra={
                        "workspace_id": workspace_id,
                        "first_seen_at": timestamp,
                        "first_ip": request_ip,
                    },
                )
                return

            first_ip_value = existing["first_ip"]
            first_ip = first_ip_value if isinstance(first_ip_value, str) else None
            if first_ip and request_ip and first_ip != request_ip:
                logger.warning(
                    "workspace handle accessed from a new IP — possible collision",
                    extra={
                        "workspace_id": workspace_id,
                        "first_ip": first_ip,
                        "first_seen_at": str(existing["first_seen_at"]),
                        "current_ip": request_ip,
                    },
                )

    def list_all(self) -> list[dict[str, str | None]]:
        with self._lock, self._connect() as conn:
            rows = _rows(conn.execute(
                """
                SELECT workspace_id, first_seen_at, first_ip
                FROM workspace_registry
                ORDER BY first_seen_at ASC
                """
            ).fetchall())
        return [
            {
                "workspaceId": str(row["workspace_id"]),
                "firstSeenAt": str(row["first_seen_at"]),
                "firstIp": (
                    str(row["first_ip"]) if row["first_ip"] is not None else None
                ),
            }
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as conn:
            _ = conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_registry (
                    workspace_id TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    first_ip TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_registry_first_seen
                    ON workspace_registry(first_seen_at);
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> str:
        return str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z"))


_registry: WorkspaceRegistry | None = None
_factory_lock = threading.Lock()


def get_workspace_registry() -> WorkspaceRegistry:
    global _registry
    if _registry is None:
        with _factory_lock:
            if _registry is None:
                _registry = WorkspaceRegistry()
    assert _registry is not None
    return _registry


__all__ = ["WorkspaceRegistry", "get_workspace_registry"]
