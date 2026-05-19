"""Background scheduler that watches trigger definitions and fires reminders."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from ..core.workspace_context import set_current_workspace
from ..logging_config import logger
from .conversation.log import get_conversation_log
from .reminders import ReminderEvent, get_reminder_event_bus
from .triggers import TriggerRecord, get_trigger_service
from .triggers.service import TriggerService
from .triggers.utils import parse_iso


UTC = timezone.utc

# Skip one-shot triggers whose due time slipped more than this far into the
# past — usually means the server was down. Recurring triggers keep their
# own "advance to next future occurrence" semantics.
MAX_REMINDER_STALENESS = timedelta(hours=6)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class TriggerScheduler:
    """Polls stored triggers and dispatches reminders when due."""

    _poll_interval: float
    _service: TriggerService
    _running: bool
    _lock: asyncio.Lock

    def __init__(self, poll_interval_seconds: float = 10.0) -> None:
        self._poll_interval = poll_interval_seconds
        self._service = get_trigger_service()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._in_flight: set[int] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            loop = asyncio.get_running_loop()
            self._running = True
            self._task = loop.create_task(self._run(), name="trigger-scheduler")
            logger.info("Trigger scheduler started", extra={"interval": self._poll_interval})

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            if self._task:
                _ = self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None
                logger.info("Trigger scheduler stopped")

    async def _run(self) -> None:
        try:
            while self._running:
                await self._poll_once()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Trigger scheduler loop crashed", extra={"error": str(exc)})

    async def _poll_once(self) -> None:
        now = _utc_now()
        due_triggers = self._service.get_due_triggers(before=now)
        if not due_triggers:
            return

        for trigger in due_triggers:
            if trigger.id in self._in_flight:
                continue
            if self._discard_if_stale(trigger, now):
                continue
            self._in_flight.add(trigger.id)
            _ = asyncio.create_task(self._fire_reminder(trigger), name=f"reminder-{trigger.id}")

    def _discard_if_stale(self, trigger: TriggerRecord, now: datetime) -> bool:
        if trigger.recurrence_rule:
            return False
        if not trigger.next_trigger:
            return False
        try:
            next_fire = parse_iso(trigger.next_trigger)
        except Exception:  # pragma: no cover - defensive
            return False
        if now - next_fire <= MAX_REMINDER_STALENESS:
            return False
        logger.warning(
            "skipping stale reminder",
            extra={
                "trigger_id": trigger.id,
                "workspace_id": trigger.workspace_id,
                "scheduled_for": trigger.next_trigger,
            },
        )
        # Order matters: mark_as_completed clears last_error, so write the
        # diagnostic afterward.
        self._service.mark_as_completed(
            trigger.id,
            agent_name=trigger.agent_name,
            workspace_id=trigger.workspace_id,
        )
        self._service.record_failure(trigger, "missed window")
        return True

    async def _fire_reminder(self, trigger: TriggerRecord) -> None:
        # Bind the ContextVar so any downstream store calls (conversation
        # log, summarization scheduler) resolve to the trigger's workspace.
        set_current_workspace(trigger.workspace_id)
        fired_at = _utc_now()
        try:
            logger.info(
                "Firing reminder",
                extra={
                    "trigger_id": trigger.id,
                    "workspace_id": trigger.workspace_id,
                    "scheduled_for": trigger.next_trigger,
                },
            )
            try:
                get_conversation_log(trigger.workspace_id).record_reminder_fired(
                    trigger.payload
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "reminder log write failed",
                    extra={"trigger_id": trigger.id, "error": str(exc)},
                )
            get_reminder_event_bus().publish(
                trigger.workspace_id,
                ReminderEvent(
                    trigger_id=trigger.id,
                    payload=trigger.payload,
                    fired_at=_isoformat(fired_at),
                ),
            )
            self._handle_success(trigger, fired_at)
        except Exception as exc:  # pragma: no cover - defensive
            self._handle_failure(trigger, _utc_now(), str(exc))
            logger.exception(
                "Reminder fire failed unexpectedly",
                extra={"trigger_id": trigger.id},
            )
        finally:
            self._in_flight.discard(trigger.id)

    def _handle_success(self, trigger: TriggerRecord, fired_at: datetime) -> None:
        logger.info(
            "Reminder fired",
            extra={"trigger_id": trigger.id, "workspace_id": trigger.workspace_id},
        )
        _ = self._service.schedule_next_occurrence(trigger, fired_at=fired_at)

    def _handle_failure(
        self, trigger: TriggerRecord, fired_at: datetime, error: str
    ) -> None:
        logger.warning(
            "Reminder fire failed",
            extra={"trigger_id": trigger.id, "error": error},
        )
        self._service.record_failure(trigger, error)
        if trigger.recurrence_rule:
            _ = self._service.schedule_next_occurrence(trigger, fired_at=fired_at)
        else:
            _ = self._service.clear_next_fire(
                trigger.id,
                agent_name=trigger.agent_name,
                workspace_id=trigger.workspace_id,
            )


_scheduler_instance: TriggerScheduler | None = None


def get_trigger_scheduler() -> TriggerScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TriggerScheduler()
    return _scheduler_instance


__all__ = ["TriggerScheduler", "get_trigger_scheduler", "MAX_REMINDER_STALENESS"]
