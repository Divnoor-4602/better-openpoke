from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, cast

from ..core.paths import get_data_dir
from ..core.sqlite_row import SqliteRow
from ..core.workspace_context import require_current_workspace
from ..domain.threads import MessageEntity, ThreadEntity
from ..utils.timezones import now_in_user_timezone


def _resolve_workspace(workspace_id: str | None) -> str:
    return workspace_id or require_current_workspace()


_DATA_DIR = get_data_dir()
_THREAD_DB_PATH = _DATA_DIR / "threads.db"


def _row(value: Any) -> SqliteRow | None:  # pyright: ignore[reportExplicitAny, reportAny]
    if value is None:
        return None
    return cast(SqliteRow, cast(object, value))


def _rows(values: Any) -> list[SqliteRow]:  # pyright: ignore[reportExplicitAny, reportAny]
    return cast("list[SqliteRow]", cast(object, values))


class ThreadNotFoundError(LookupError):
    pass


class ThreadRepository:
    _db_path: Path
    _lock: threading.Lock

    def __init__(self, db_path: Path = _THREAD_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def create_thread(self, *, workspace_id: str | None = None) -> ThreadEntity:
        workspace_id = _resolve_workspace(workspace_id)
        thread_id = str(uuid.uuid4())
        timestamp = self._now()
        with self._lock, self._connect() as conn:
            _ = conn.execute(
                """
                INSERT INTO threads (workspace_id, thread_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, thread_id, None, timestamp, timestamp),
            )
            conn.commit()
        return ThreadEntity(
            thread_id=thread_id,
            title=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def list_threads(
        self, *, workspace_id: str | None = None, offset: int, limit: int
    ) -> tuple[list[ThreadEntity], int | None]:
        workspace_id = _resolve_workspace(workspace_id)
        safe_limit = max(1, min(limit, 100))
        normalized_offset = max(0, offset)
        with self._lock, self._connect() as conn:
            rows = _rows(conn.execute(
                """
                SELECT *
                FROM threads
                WHERE workspace_id = ?
                ORDER BY updated_at DESC, thread_id DESC
                LIMIT ? OFFSET ?
                """,
                (workspace_id, safe_limit + 1, normalized_offset),
            ).fetchall())
        items = [self._thread_from_row(row) for row in rows]
        next_offset = (
            normalized_offset + safe_limit if len(items) > safe_limit else None
        )
        return items[:safe_limit], next_offset

    def get_thread(
        self, thread_id: str, *, workspace_id: str | None = None
    ) -> ThreadEntity | None:
        workspace_id = _resolve_workspace(workspace_id)
        with self._lock, self._connect() as conn:
            row = _row(conn.execute(
                "SELECT * FROM threads WHERE workspace_id = ? AND thread_id = ?",
                (workspace_id, thread_id),
            ).fetchone())
        return self._thread_from_row(row) if row is not None else None

    def update_thread(
        self, thread_id: str, *, workspace_id: str | None = None, title: str
    ) -> ThreadEntity:
        workspace_id = _resolve_workspace(workspace_id)
        timestamp = self._now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE threads
                SET title = ?, updated_at = ?
                WHERE workspace_id = ? AND thread_id = ?
                """,
                (title, timestamp, workspace_id, thread_id),
            )
            if cursor.rowcount == 0:
                raise ThreadNotFoundError(thread_id)
            row = _row(conn.execute(
                "SELECT * FROM threads WHERE workspace_id = ? AND thread_id = ?",
                (workspace_id, thread_id),
            ).fetchone())
            conn.commit()
        assert row is not None
        return self._thread_from_row(row)

    def delete_thread(self, thread_id: str, *, workspace_id: str | None = None) -> None:
        workspace_id = _resolve_workspace(workspace_id)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM threads WHERE workspace_id = ? AND thread_id = ?",
                (workspace_id, thread_id),
            )
            if cursor.rowcount == 0:
                raise ThreadNotFoundError(thread_id)
            conn.commit()

    def create_message(
        self,
        thread_id: str,
        *,
        workspace_id: str | None = None,
        role: str,
        content: str,
        parts: list[dict[str, object]] | None = None,
        turn_index: int | None = None,
    ) -> MessageEntity:
        """Insert a message into the thread.

        `turn_index` orders messages so that an assistant turn always sorts
        after the user turn that triggered it, even when concurrent turns
        commit out of chronological order. Pass `None` to auto-assign
        (max(existing) + 1 for this thread). Pass an explicit value to
        co-locate an assistant message with the user message it answers.
        """
        workspace_id = _resolve_workspace(workspace_id)
        message_id = str(uuid.uuid4())
        timestamp = self._now()
        parts_json = (
            json.dumps(parts, ensure_ascii=False) if parts is not None else None
        )
        with self._lock, self._connect() as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM threads WHERE workspace_id = ? AND thread_id = ?",
                    (workspace_id, thread_id),
                ).fetchone()
                is None
            ):
                raise ThreadNotFoundError(thread_id)
            if turn_index is None:
                next_row = _row(conn.execute(
                    """
                    SELECT COALESCE(MAX(turn_index), -1) + 1 AS next_idx
                    FROM messages
                    WHERE workspace_id = ? AND thread_id = ?
                    """,
                    (workspace_id, thread_id),
                ).fetchone())
                resolved_turn_index = (
                    int(cast(int, next_row["next_idx"])) if next_row is not None else 0
                )
            else:
                resolved_turn_index = turn_index
            try:
                _ = conn.execute(
                    """
                    INSERT INTO messages (
                        workspace_id, message_id, thread_id, role, content, parts_json,
                        created_at, turn_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_id,
                        message_id,
                        thread_id,
                        role,
                        content,
                        parts_json,
                        timestamp,
                        resolved_turn_index,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ThreadNotFoundError(thread_id) from exc
            _ = conn.execute(
                "UPDATE threads SET updated_at = ? WHERE workspace_id = ? AND thread_id = ?",
                (timestamp, workspace_id, thread_id),
            )
            conn.commit()
        return MessageEntity(
            message_id=message_id,
            thread_id=thread_id,
            role=role,
            content=content,
            parts_json=parts_json,
            created_at=timestamp,
            turn_index=resolved_turn_index,
        )

    def list_messages(
        self,
        thread_id: str,
        *,
        workspace_id: str | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[MessageEntity], int | None]:
        workspace_id = _resolve_workspace(workspace_id)
        if self.get_thread(thread_id, workspace_id=workspace_id) is None:
            raise ThreadNotFoundError(thread_id)
        safe_limit = max(1, min(limit, 100))
        normalized_offset = max(0, offset)
        with self._lock, self._connect() as conn:
            rows = _rows(conn.execute(
                """
                SELECT *
                FROM messages
                WHERE workspace_id = ? AND thread_id = ?
                ORDER BY turn_index ASC, created_at ASC, message_id ASC
                LIMIT ? OFFSET ?
                """,
                (workspace_id, thread_id, safe_limit + 1, normalized_offset),
            ).fetchall())
        items = [self._message_from_row(row) for row in rows]
        next_offset = (
            normalized_offset + safe_limit if len(items) > safe_limit else None
        )
        return items[:safe_limit], next_offset

    def clear_all(self) -> None:
        """Dev-only: wipe every workspace's data. Used by the dev reset route."""
        with self._lock, self._connect() as conn:
            _ = conn.execute("DELETE FROM messages")
            _ = conn.execute("DELETE FROM threads")
            conn.commit()

    def clear_workspace(self, workspace_id: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            _ = conn.execute(
                "DELETE FROM messages WHERE workspace_id = ?", (workspace_id,)
            )
            _ = conn.execute(
                "DELETE FROM threads WHERE workspace_id = ?", (workspace_id,)
            )
            conn.commit()

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            _ = conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    workspace_id TEXT NOT NULL,
                    thread_id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    workspace_id TEXT NOT NULL,
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parts_json TEXT,
                    created_at TEXT NOT NULL,
                    turn_index INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_threads_workspace_updated
                ON threads (workspace_id, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_messages_workspace_thread_turn
                ON messages (workspace_id, thread_id, turn_index, created_at);
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _ = conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _thread_from_row(self, row: SqliteRow) -> ThreadEntity:
        raw_title = row["title"]
        return ThreadEntity(
            thread_id=str(row["thread_id"]),
            title=str(raw_title) if raw_title is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _message_from_row(self, row: SqliteRow) -> MessageEntity:
        try:
            turn_index_value: object = row["turn_index"]
        except (IndexError, KeyError):
            turn_index_value = 0
        parts_json_value = row["parts_json"]
        return MessageEntity(
            message_id=str(row["message_id"]),
            thread_id=str(row["thread_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            parts_json=parts_json_value if isinstance(parts_json_value, str) else None,
            created_at=str(row["created_at"]),
            turn_index=int(cast(int, turn_index_value))
            if turn_index_value is not None
            else 0,
        )

    def _now(self) -> str:
        return str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z"))


_thread_repository = ThreadRepository(_THREAD_DB_PATH)


def get_thread_repository() -> ThreadRepository:
    return _thread_repository
