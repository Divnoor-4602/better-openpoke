"""Gmail-related service helpers."""

from __future__ import annotations

from typing import Any

from .client import (
    disconnect_account,
    execute_gmail_tool,
    fetch_status,
    get_active_gmail_user_id,
    initiate_connect,
)
from .importance_classifier import classify_email_importance
from .processing import EmailTextCleaner, ProcessedEmail, parse_gmail_fetch_response
from .seen_store import GmailSeenStore


def __getattr__(name: str) -> Any:
    if name in {"ImportantEmailWatcher", "get_important_email_watcher"}:
        from .importance_watcher import ImportantEmailWatcher, get_important_email_watcher

        exports = {
            "ImportantEmailWatcher": ImportantEmailWatcher,
            "get_important_email_watcher": get_important_email_watcher,
        }
        return exports[name]
    raise AttributeError(name)

__all__ = [
    "execute_gmail_tool",
    "fetch_status",
    "initiate_connect",
    "disconnect_account",
    "get_active_gmail_user_id",
    "classify_email_importance",
    "ImportantEmailWatcher",
    "get_important_email_watcher",
    "EmailTextCleaner",
    "ProcessedEmail",
    "parse_gmail_fetch_response",
    "GmailSeenStore",
]
