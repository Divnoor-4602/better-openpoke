"""Persist and expose each workspace's preferred timezone."""

from __future__ import annotations

import threading
from pathlib import Path

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..core.paths import get_data_dir
from ..core.workspace_context import require_current_workspace
from ..logging_config import logger


class TimezoneStore:
    """Stores a single timezone string supplied by the client UI."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._lock: threading.Lock = threading.Lock()
        self._cached: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            value = self._path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            self._cached = None
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("failed to read timezone file", extra={"error": str(exc)})
            self._cached = None
            return

        self._cached = value or None

    def get_timezone(self, default: str = "UTC") -> str:
        with self._lock:
            return self._cached or default

    def set_timezone(self, timezone_name: str) -> None:
        validated = self._validate(timezone_name)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            _ = self._path.write_text(validated, encoding="utf-8")
            self._cached = validated
            logger.info(
                "updated timezone preference",
                extra={"timezone": validated, "path": str(self._path)},
            )

    def clear(self) -> None:
        with self._lock:
            self._cached = None
            try:
                if self._path.exists():
                    _ = self._path.unlink()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "failed to clear timezone file", extra={"error": str(exc)}
                )

    def _validate(self, timezone_name: str) -> str:
        candidate = (timezone_name or "").strip()
        if not candidate:
            raise ValueError("timezone must be a non-empty string")
        try:
            _ = ZoneInfo(candidate)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {candidate}") from exc
        return candidate


_DATA_DIR = get_data_dir()
_TIMEZONE_DIR = _DATA_DIR / "timezone"

_cache: dict[str, TimezoneStore] = {}
_cache_lock = threading.Lock()


def _resolve_workspace(workspace_id: str | None) -> str:
    return workspace_id or require_current_workspace()


def get_timezone_store(workspace_id: str | None = None) -> TimezoneStore:
    workspace_id = _resolve_workspace(workspace_id)
    cached = _cache.get(workspace_id)
    if cached is not None:
        return cached
    with _cache_lock:
        cached = _cache.get(workspace_id)
        if cached is None:
            path = _TIMEZONE_DIR / f"{workspace_id}.txt"
            cached = TimezoneStore(path)
            _cache[workspace_id] = cached
        return cached


def reset_timezone_cache() -> None:
    """Test helper: clear the per-workspace cache."""
    with _cache_lock:
        _cache.clear()


__all__ = ["TimezoneStore", "get_timezone_store", "reset_timezone_cache"]
