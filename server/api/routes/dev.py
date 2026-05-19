from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...core.errors import ERROR_RESPONSES
from ...db.threads import get_thread_repository
from ...services.conversation.log import get_conversation_log
from ...services.conversation.summarization.scheduler import (
    reset_workspace as reset_summarization_workspace,
)
from ...services.conversation.summarization.working_memory_log import (
    get_working_memory_log,
)
from ...services.execution.event_store import get_execution_event_store
from ...services.execution.log_store import get_execution_agent_logs
from ...services.gmail.connections import (
    unregister_workspace as unregister_gmail_workspace,
)
from ...services.gmail.importance_watcher import get_important_email_watcher
from ...services.memory.indexer import clear_pinecone_workspace
from ...services.memory.store import get_memory_store
from ...services.timezone_store import get_timezone_store
from ...services.triggers import get_trigger_service
from ..dependencies import get_workspace_id

router = APIRouter(tags=["dev"], responses=ERROR_RESPONSES)


class ResetResponse(BaseModel):
    ok: bool
    cleared: list[str]


@router.post(
    "/dev/reset",
    response_model=ResetResponse,
    operation_id="dev_reset",
    summary="Truncate dev tables and clear conversation logs for the caller's workspace",
)
def dev_reset(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
) -> ResetResponse:
    cleared: list[str] = []
    errors: list[str] = []

    targets = [
        ("threads", lambda: get_thread_repository().clear_workspace(workspace_id)),
        (
            "execution_events",
            lambda: (
                get_execution_event_store().clear_workspace(workspace_id)
                if hasattr(get_execution_event_store(), "clear_workspace")
                else get_execution_event_store().clear_all()
            ),
        ),
        ("memory", lambda: get_memory_store().clear_workspace(workspace_id)),
        ("pinecone_namespace", lambda: clear_pinecone_workspace(workspace_id)),
        (
            "triggers",
            lambda: get_trigger_service().clear_workspace(workspace_id),
        ),
        ("conversation_log", lambda: get_conversation_log(workspace_id).clear()),
        ("timezone", lambda: get_timezone_store(workspace_id).clear()),
        ("execution_logs", lambda: get_execution_agent_logs(workspace_id).clear_all()),
        ("working_memory", lambda: get_working_memory_log(workspace_id).clear()),
        (
            "gmail_seen",
            lambda: get_important_email_watcher().reset_workspace(workspace_id),
        ),
        ("gmail_registry", lambda: unregister_gmail_workspace(workspace_id)),
        (
            "summarization_scheduler",
            lambda: reset_summarization_workspace(workspace_id),
        ),
    ]

    for name, fn in targets:
        try:
            _ = fn()
            cleared.append(name)
        except Exception as exc:  # noqa: BLE001 — dev endpoint, report and continue
            errors.append(f"{name}: {exc}")

    if errors and not cleared:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(errors),
        )
    return ResetResponse(ok=not errors, cleared=cleared + [f"!{e}" for e in errors])
