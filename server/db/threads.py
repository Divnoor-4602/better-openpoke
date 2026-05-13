from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, cast

from ..domain.threads import MessageEntity, ThreadEntity
from ..utils.timezones import now_in_user_timezone

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_THREAD_DB_PATH = _DATA_DIR / "threads.db"


class ThreadNotFoundError(LookupError):
    pass


class ThreadRepository:
    def __init__(self, db_path: Path = _THREAD_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def create_thread(self) -> ThreadEntity:
        thread_id = str(uuid.uuid4())
        timestamp = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO threads (thread_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (thread_id, thread_id, timestamp, timestamp),
            )
            conn.commit()
        return ThreadEntity(
            thread_id=thread_id,
            title=thread_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def list_threads(self, *, offset: int, limit: int) -> tuple[list[ThreadEntity], int | None]:
        safe_limit = max(1, min(limit, 100))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM threads
                ORDER BY updated_at DESC, thread_id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit + 1, max(0, offset)),
            ).fetchall()
        items = [self._thread_from_row(row) for row in cast(list[sqlite3.Row], rows)]
        next_offset = offset + safe_limit if len(items) > safe_limit else None
        return items[:safe_limit], next_offset

    def get_thread(self, thread_id: str) -> ThreadEntity | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return self._thread_from_row(cast(sqlite3.Row, row)) if row is not None else None

    def update_thread(self, thread_id: str, *, title: str) -> ThreadEntity:
        timestamp = self._now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE threads
                SET title = ?, updated_at = ?
                WHERE thread_id = ?
                """,
                (title, timestamp, thread_id),
            )
            if cursor.rowcount == 0:
                raise ThreadNotFoundError(thread_id)
            row = conn.execute(
                "SELECT * FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            conn.commit()
        return self._thread_from_row(cast(sqlite3.Row, row))

    def delete_thread(self, thread_id: str) -> None:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
            if cursor.rowcount == 0:
                raise ThreadNotFoundError(thread_id)
            conn.commit()

    def create_message(
        self,
        thread_id: str,
        *,
        role: str,
        content: str,
        parts: list[dict[str, Any]] | None = None,
    ) -> MessageEntity:
        if self.get_thread(thread_id) is None:
            raise ThreadNotFoundError(thread_id)
        message_id = str(uuid.uuid4())
        timestamp = self._now()
        parts_json = json.dumps(parts, ensure_ascii=False) if parts is not None else None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    message_id, thread_id, role, content, parts_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, thread_id, role, content, parts_json, timestamp),
            )
            conn.execute(
                "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
                (timestamp, thread_id),
            )
            conn.commit()
        return MessageEntity(
            message_id=message_id,
            thread_id=thread_id,
            role=role,
            content=content,
            parts_json=parts_json,
            created_at=timestamp,
        )

    def list_messages(
        self, thread_id: str, *, offset: int, limit: int
    ) -> tuple[list[MessageEntity], int | None]:
        if self.get_thread(thread_id) is None:
            raise ThreadNotFoundError(thread_id)
        safe_limit = max(1, min(limit, 100))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE thread_id = ?
                ORDER BY created_at ASC, message_id ASC
                LIMIT ? OFFSET ?
                """,
                (thread_id, safe_limit + 1, max(0, offset)),
            ).fetchall()
        items = [self._message_from_row(row) for row in cast(list[sqlite3.Row], rows)]
        next_offset = offset + safe_limit if len(items) > safe_limit else None
        return items[:safe_limit], next_offset

    def clear_all(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM threads")
            conn.commit()

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parts_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_threads_updated
                ON threads (updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_messages_thread_created
                ON messages (thread_id, created_at ASC);
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _thread_from_row(self, row: sqlite3.Row) -> ThreadEntity:
        return ThreadEntity(
            thread_id=str(row["thread_id"]),
            title=str(row["title"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _message_from_row(self, row: sqlite3.Row) -> MessageEntity:
        return MessageEntity(
            message_id=str(row["message_id"]),
            thread_id=str(row["thread_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            parts_json=cast(str | None, row["parts_json"]),
            created_at=str(row["created_at"]),
        )

    def _now(self) -> str:
        return str(now_in_user_timezone("%Y-%m-%dT%H:%M:%S%z"))


_thread_repository = ThreadRepository(_THREAD_DB_PATH)


def get_thread_repository() -> ThreadRepository:
    return _thread_repository

