from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ...agents.interaction_agent.runtime import InteractionAgentRuntime
from ...core.errors import ERROR_RESPONSES
from ...core.pagination import CursorPage, decode_cursor, encode_cursor
from ...db.threads import ThreadNotFoundError, ThreadRepository, get_thread_repository
from ...logging_config import logger
from ...services.conversation.title_generator import (
    OpenRouterError,
)
from ...services.conversation.title_generator import (
    generate_thread_title as generate_title_for_thread,
)
from ...services.execution import get_execution_event_store
from ...services.timezone_store import get_timezone_store
from ..converters import agent_run_resource, message_resource, thread_resource
from ..schemas import (
    AgentRunCreateRequest,
    AgentRunListResponse,
    AgentRunResponse,
    DeleteResponse,
    MessageCreateRequest,
    MessageCreateResponse,
    MessageListResponse,
    MessageStreamRequest,
    ThreadCreateResponse,
    ThreadListResponse,
    ThreadResponse,
    ThreadUpdateRequest,
    UIMessage,
)

router = APIRouter(prefix="/threads", tags=["threads"], responses=ERROR_RESPONSES)


@router.post(
    "",
    response_model=ThreadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_thread",
    summary="Create a thread",
)
def create_thread(
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> ThreadCreateResponse:
    return ThreadCreateResponse(thread=thread_resource(repository.create_thread()))


@router.get(
    "",
    response_model=ThreadListResponse,
    operation_id="list_threads",
    summary="List threads",
)
def list_threads(
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ThreadListResponse:
    offset = decode_cursor(cursor)
    threads, next_offset = repository.list_threads(offset=offset, limit=limit)
    return ThreadListResponse(
        items=[thread_resource(thread) for thread in threads],
        page=CursorPage(nextCursor=encode_cursor(next_offset), limit=limit),
    )


@router.get(
    "/{threadId}",
    response_model=ThreadResponse,
    operation_id="retrieve_thread",
    summary="Get a thread",
)
def retrieve_thread(
    threadId: str,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> ThreadResponse:
    thread = repository.get_thread(threadId)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )
    return ThreadResponse(thread=thread_resource(thread))


@router.patch(
    "/{threadId}",
    response_model=ThreadResponse,
    operation_id="update_thread",
    summary="Update a thread",
)
def update_thread(
    threadId: str,
    payload: ThreadUpdateRequest,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> ThreadResponse:
    trimmed_title = payload.title.strip()
    if trimmed_title == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title must not be empty or whitespace only",
        )
    try:
        thread = repository.update_thread(threadId, title=trimmed_title)
    except ThreadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    return ThreadResponse(thread=thread_resource(thread))


async def _safe_generate_title(thread_id: str, repository: ThreadRepository) -> None:
    try:
        _ = await generate_title_for_thread(thread_id, repository=repository)
    except Exception:
        logger.exception(
            "background thread title generation failed",
            extra={"thread_id": thread_id},
        )


@router.post(
    "/{threadId}/title",
    response_model=ThreadResponse,
    operation_id="generate_thread_title",
    summary="Generate a thread title",
)
async def generate_thread_title(
    threadId: str,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> ThreadResponse:
    if repository.get_thread(threadId) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )
    try:
        _ = await generate_title_for_thread(threadId, repository=repository)
    except ThreadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    except OpenRouterError as exc:
        # Let the global Exception handler log with traceback; we just need to
        # translate to a 500 with a user-facing message.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Thread title generation failed",
        ) from exc

    thread = repository.get_thread(threadId)
    if thread is None:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )
    return ThreadResponse(thread=thread_resource(thread))


@router.delete(
    "/{threadId}",
    response_model=DeleteResponse,
    operation_id="delete_thread",
    summary="Delete a thread",
)
def delete_thread(
    threadId: str,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> DeleteResponse:
    try:
        repository.delete_thread(threadId)
    except ThreadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    return DeleteResponse()


@router.get(
    "/{threadId}/messages",
    response_model=MessageListResponse,
    operation_id="list_thread_messages",
    summary="List thread messages",
)
def list_thread_messages(
    threadId: str,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessageListResponse:
    try:
        messages, next_offset = repository.list_messages(
            threadId,
            offset=decode_cursor(cursor),
            limit=limit,
        )
    except ThreadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    return MessageListResponse(
        items=[message_resource(message) for message in messages],
        page=CursorPage(nextCursor=encode_cursor(next_offset), limit=limit),
    )


@router.post(
    "/{threadId}/messages",
    response_model=MessageCreateResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_thread_message",
    summary="Create a thread message",
)
def create_thread_message(
    threadId: str,
    payload: MessageCreateRequest,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> MessageCreateResponse:
    message = payload.message
    content = message.text_content()
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing message content"
        )
    try:
        created = repository.create_message(
            threadId,
            role=message.role,
            content=content,
            parts=message.serializable_parts(),
        )
    except ThreadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc
    return MessageCreateResponse(message=message_resource(created))


@router.post(
    "/{threadId}/messages/stream",
    response_model=None,
    responses={
        200: {
            "description": "AI SDK UI message stream containing text/reasoning/tool chunks and data-agent-event lifecycle chunks",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **ERROR_RESPONSES,
    },
    operation_id="stream_thread_message",
    summary="Submit a message and stream UI parts",
)
async def stream_thread_message(
    threadId: str,
    payload: MessageStreamRequest,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> StreamingResponse:
    if repository.get_thread(threadId) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    user_message = _latest_user_message(payload.messages)
    if user_message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user message"
        )

    user_content = user_message.text_content()
    if not user_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing message content"
        )

    if payload.timezone:
        try:
            get_timezone_store().set_timezone(payload.timezone)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    try:
        user_record = repository.create_message(
            threadId,
            role="user",
            content=user_content,
            parts=user_message.serializable_parts(),
        )
        runtime = InteractionAgentRuntime()
    except ThreadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    async def _streaming():
        async for chunk in runtime.stream_execute(
            user_content,
            thread_id=threadId,
            turn_index=user_record.turn_index,
            notifications=payload.notifications,
        ):
            yield chunk
        _ = asyncio.create_task(_safe_generate_title(threadId, repository))

    return StreamingResponse(
        _streaming(),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "cache-control": "no-cache",
        },
    )


@router.get(
    "/{threadId}/agent-runs",
    response_model=AgentRunListResponse,
    operation_id="list_thread_agent_runs",
    summary="List agent runs for a thread",
)
def list_thread_agent_runs(
    threadId: str,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> AgentRunListResponse:
    if repository.get_thread(threadId) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    offset = decode_cursor(cursor)
    runs = get_execution_event_store().list_runs(
        limit=limit + 1,
        offset=offset,
        thread_id=threadId,
    )
    page_items = runs[:limit]
    next_offset = offset + limit if len(runs) > limit else None
    return AgentRunListResponse(
        items=[agent_run_resource(run) for run in page_items],
        page=CursorPage(nextCursor=encode_cursor(next_offset), limit=limit),
    )


@router.post(
    "/{threadId}/agent-runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="create_thread_agent_run",
    summary="Create an agent run for a thread",
)
def create_thread_agent_run(
    threadId: str,
    payload: AgentRunCreateRequest,
    repository: Annotated[ThreadRepository, Depends(get_thread_repository)],
) -> AgentRunResponse:
    if repository.get_thread(threadId) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    store = get_execution_event_store()
    request_id = payload.requestId or str(uuid.uuid4())
    store.record_submitted(
        request_id=request_id,
        memory_id=payload.memoryId,
        title=payload.title or payload.memoryId,
        instructions=payload.instructions,
        parent_memory_id=payload.parentMemoryId,
        thread_id=threadId,
    )
    run = store.get_run(request_id)
    if run is None:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent run not found",
        )
    return AgentRunResponse(run=agent_run_resource(run))


def _latest_user_message(messages: list[UIMessage]) -> UIMessage | None:
    for message in reversed(messages):
        if message.role == "user" and message.text_content().strip():
            return message
    return None
