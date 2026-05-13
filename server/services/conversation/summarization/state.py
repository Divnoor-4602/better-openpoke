from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LogEntry:
    """Snapshot of a single conversation log entry."""

    tag: str
    payload: str
    index: int = -1
    timestamp: str | None = None


@dataclass
class SummaryState:
    """Persisted working-memory summary state."""

    summary_text: str = ""
    last_index: int = -1
    updated_at: datetime | None = None
    unsummarized_entries: list[LogEntry] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "SummaryState":
        return cls()


__all__ = ["LogEntry", "SummaryState"]
