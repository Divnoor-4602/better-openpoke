"""Direct Gmail draft mutations for the REST layer.

These functions wrap Composio's ``GOOGLESUPER_*`` draft actions for use by
``server/api/routes/gmail/drafts.py``. They are intentionally separate from
the LLM-tool wrappers in ``server/agents/execution_agent/tools/gmail.py``,
which return agent-shaped payloads and write to memory/journals. The REST
handlers just need the raw normalized Composio response plus a clear
"not connected" signal.
"""

from __future__ import annotations

from .client import (
    JsonDict,
    execute_google_tool,
    resolve_workspace_gmail_user_id,
)


class GmailNotConnectedError(RuntimeError):
    """Raised when no active Google connection exists for the current user."""


def _require_user() -> str:
    user_id = resolve_workspace_gmail_user_id()
    if not user_id:
        raise GmailNotConnectedError("No active Google connection")
    return user_id


def send_draft(draft_id: str) -> JsonDict:
    """Send a previously-created draft via ``GOOGLESUPER_SEND_DRAFT``."""
    return execute_google_tool(
        "GOOGLESUPER_SEND_DRAFT",
        _require_user(),
        arguments={"draft_id": draft_id},
    )


def update_draft(draft_id: str, fields: dict[str, object]) -> JsonDict:
    """Patch a draft via ``GOOGLESUPER_UPDATE_DRAFT``.

    ``fields`` is a flat partial — ``subject``, ``body``, ``to``, ``cc``,
    ``bcc`` are all optional. Only non-``None`` values are forwarded so a
    partial PATCH doesn't accidentally clear unset fields on Gmail's side.
    """
    message: dict[str, object] = {
        key: value for key, value in fields.items() if value is not None
    }
    return execute_google_tool(
        "GOOGLESUPER_UPDATE_DRAFT",
        _require_user(),
        arguments={"draft_id": draft_id, "message": message},
    )


def discard_draft(draft_id: str) -> JsonDict:
    """Delete a draft via ``GOOGLESUPER_DELETE_DRAFT``."""
    return execute_google_tool(
        "GOOGLESUPER_DELETE_DRAFT",
        _require_user(),
        arguments={"draft_id": draft_id},
    )
