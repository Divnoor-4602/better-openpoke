"""Re-export for the Google Composio tool executor.

The actual implementation lives alongside the shared Composio singleton in
`server.services.gmail.client`. This module exists so new callers can import
from the more semantically correct ``services.google.client`` path without
having to follow the legacy ``services.gmail`` location.
"""

from __future__ import annotations

from ..gmail.client import execute_google_tool

__all__ = ["execute_google_tool"]
