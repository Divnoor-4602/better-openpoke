"""Background watcher that surfaces important Gmail emails proactively."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.paths import get_data_dir
from ...core.workspace_context import set_current_workspace
from ...logging_config import logger
from ...utils.timezones import convert_to_user_timezone
from .client import execute_google_tool
from .connections import list_workspaces_with_gmail
from .importance_classifier import classify_email_importance
from .processing import EmailTextCleaner, ProcessedEmail, parse_gmail_fetch_response
from .seen_store import GmailSeenStore

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime


def _resolve_interaction_runtime() -> "InteractionAgentRuntime":
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

    return InteractionAgentRuntime()


DEFAULT_POLL_INTERVAL_SECONDS = 60.0
DEFAULT_LOOKBACK_MINUTES = 10
DEFAULT_MAX_RESULTS = 50
DEFAULT_SEEN_LIMIT = 300
PER_WORKSPACE_TIMEOUT_SECONDS = 30.0


_DATA_DIR = get_data_dir()
_SEEN_DIR = _DATA_DIR / "gmail_seen"


def _seen_store_path(workspace_id: str) -> Path:
    return _SEEN_DIR / f"{workspace_id}.json"


class _WorkspaceState:
    """Per-workspace polling state (seen-store + bookkeeping)."""

    __slots__: tuple[str, ...] = ("seen_store", "has_seeded_initial_snapshot", "last_poll_timestamp")

    def __init__(self, workspace_id: str) -> None:
        self.seen_store: GmailSeenStore = GmailSeenStore(
            _seen_store_path(workspace_id), DEFAULT_SEEN_LIMIT
        )
        self.has_seeded_initial_snapshot: bool = False
        self.last_poll_timestamp: datetime | None = None


class ImportantEmailWatcher:
    """Poll Gmail for recent messages and surface important ones, per workspace."""

    def __init__(
        self,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    ) -> None:
        self._poll_interval: float = poll_interval_seconds
        self._lookback_minutes: int = lookback_minutes
        self._lock: asyncio.Lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._cleaner: EmailTextCleaner = EmailTextCleaner(max_url_length=60)
        self._workspace_state: dict[str, _WorkspaceState] = {}

    def _state_for(self, workspace_id: str) -> _WorkspaceState:
        state = self._workspace_state.get(workspace_id)
        if state is None:
            state = _WorkspaceState(workspace_id)
            self._workspace_state[workspace_id] = state
        return state

    # Start the background email polling task
    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            loop = asyncio.get_running_loop()
            self._running = True
            self._workspace_state.clear()
            self._task = loop.create_task(self._run(), name="important-email-watcher")
            logger.info(
                "Important email watcher started",
                extra={
                    "interval_seconds": self._poll_interval,
                    "lookback_minutes": self._lookback_minutes,
                },
            )

    # Stop the background email polling task gracefully
    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            if self._task:
                _ = self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._task = None
                logger.info("Important email watcher stopped")

    def reset_workspace(self, workspace_id: str) -> None:
        """Drop a workspace's in-memory poll state and its seen-store file.

        Used by `/dev/reset`. After this, the next poll behaves like the
        workspace's first poll (initial-snapshot warmup again).
        """
        _ = self._workspace_state.pop(workspace_id, None)
        try:
            path = _seen_store_path(workspace_id)
            if path.exists():
                path.unlink()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "gmail seen-store reset failed",
                extra={"workspace_id": workspace_id, "error": str(exc)},
            )

    async def _run(self) -> None:
        try:
            while self._running:
                workspaces = list_workspaces_with_gmail()
                for workspace_id in workspaces:
                    if not self._running:
                        break
                    try:
                        await asyncio.wait_for(
                            self._poll_workspace(workspace_id),
                            timeout=PER_WORKSPACE_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Important email watcher tick timed out",
                            extra={
                                "workspace_id": workspace_id,
                                "timeout": PER_WORKSPACE_TIMEOUT_SECONDS,
                            },
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception(
                            "Important email watcher poll failed",
                            extra={
                                "workspace_id": workspace_id,
                                "error": str(exc),
                            },
                        )
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise

    # Poll Gmail once for new messages and classify them for importance
    def _complete_poll(self, state: _WorkspaceState, user_now: datetime) -> None:
        state.last_poll_timestamp = user_now
        state.has_seeded_initial_snapshot = True

    async def _poll_workspace(self, workspace_id: str) -> None:
        # Bind ContextVar so any downstream store calls (memory, conversation
        # log, timezone) resolve to this workspace.
        set_current_workspace(workspace_id)
        state = self._state_for(workspace_id)

        poll_started_at = datetime.now(timezone.utc)
        user_now = convert_to_user_timezone(poll_started_at)
        first_poll = not state.has_seeded_initial_snapshot
        previous_poll_timestamp = state.last_poll_timestamp
        interval_cutoff = user_now - timedelta(seconds=self._poll_interval)
        cutoff_time = interval_cutoff
        if (
            previous_poll_timestamp is not None
            and previous_poll_timestamp > interval_cutoff
        ):
            cutoff_time = previous_poll_timestamp

        # Composio user_id is the workspace_id by design (see integrations route).
        composio_user_id = workspace_id

        query = f"label:INBOX newer_than:{self._lookback_minutes}m"
        arguments = {
            "query": query,
            "include_payload": True,
            "max_results": DEFAULT_MAX_RESULTS,
        }

        try:
            raw_result = execute_google_tool(
                "GOOGLESUPER_FETCH_EMAILS", composio_user_id, arguments=arguments
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch Gmail messages for watcher",
                extra={"workspace_id": workspace_id, "error": str(exc)},
            )
            return

        processed_emails, _ = parse_gmail_fetch_response(
            raw_result,
            query=query,
            cleaner=self._cleaner,
        )

        if not processed_emails:
            logger.debug(
                "No recent Gmail messages found for watcher",
                extra={"workspace_id": workspace_id},
            )
            self._complete_poll(state, user_now)
            return

        if first_poll:
            state.seen_store.mark_seen(email.id for email in processed_emails)
            logger.info(
                "Important email watcher completed initial warmup",
                extra={
                    "workspace_id": workspace_id,
                    "skipped_ids": len(processed_emails),
                },
            )
            self._complete_poll(state, user_now)
            return

        unseen_emails: list[ProcessedEmail] = [
            email
            for email in processed_emails
            if not state.seen_store.is_seen(email.id)
        ]

        if not unseen_emails:
            logger.info(
                "Important email watcher check complete",
                extra={
                    "workspace_id": workspace_id,
                    "emails_reviewed": 0,
                    "surfaced": 0,
                },
            )
            self._complete_poll(state, user_now)
            return

        unseen_emails.sort(
            key=lambda email: email.timestamp or datetime.now(timezone.utc)
        )

        eligible_emails: list[ProcessedEmail] = []
        aged_emails: list[ProcessedEmail] = []

        for email in unseen_emails:
            email_timestamp = email.timestamp
            if email_timestamp.tzinfo is not None:
                email_timestamp = email_timestamp.astimezone(user_now.tzinfo)
            else:
                email_timestamp = email_timestamp.replace(tzinfo=user_now.tzinfo)

            if email_timestamp < cutoff_time:
                aged_emails.append(email)
                continue

            eligible_emails.append(email)

        if not eligible_emails and aged_emails:
            state.seen_store.mark_seen(email.id for email in aged_emails)
            logger.info(
                "Important email watcher check complete",
                extra={
                    "workspace_id": workspace_id,
                    "emails_reviewed": len(unseen_emails),
                    "surfaced": 0,
                    "suppressed_for_age": len(aged_emails),
                },
            )
            self._complete_poll(state, user_now)
            return

        summaries_sent = 0
        processed_ids: list[str] = [email.id for email in aged_emails]

        for email in eligible_emails:
            summary = await classify_email_importance(email)
            processed_ids.append(email.id)
            if not summary:
                continue

            summaries_sent += 1
            await self._dispatch_summary(summary)

        if processed_ids:
            state.seen_store.mark_seen(processed_ids)

        logger.info(
            "Important email watcher check complete",
            extra={
                "workspace_id": workspace_id,
                "emails_reviewed": len(unseen_emails),
                "surfaced": summaries_sent,
                "suppressed_for_age": len(aged_emails),
            },
        )
        self._complete_poll(state, user_now)

    async def _dispatch_summary(self, summary: str) -> None:
        # ContextVar is already bound to the polling workspace at this point.
        runtime = _resolve_interaction_runtime()
        try:
            contextualized = f"Important email watcher notification:\n{summary}"
            _ = await runtime.handle_agent_message(contextualized)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to dispatch important email summary",
                extra={"error": str(exc)},
            )


_watcher_instance: ImportantEmailWatcher | None = None


def get_important_email_watcher() -> ImportantEmailWatcher:
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = ImportantEmailWatcher()
    return _watcher_instance


__all__ = ["ImportantEmailWatcher", "get_important_email_watcher"]
