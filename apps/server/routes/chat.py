from typing import cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from ..agents.interaction_agent.runtime import InteractionAgentRuntime
from ..logging_config import logger
from ..models import (
    ChatHistoryClearResponse,
    ChatHistoryResponse,
    ChatMessage,
    ChatRequest,
)
from ..services.conversation.chat_handler import handle_chat_request
from ..services.conversation.log import get_conversation_log
from ..services.triggers import get_trigger_service
from ..utils.responses import error_response

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/send",
    response_class=JSONResponse,
    response_model=None,
    summary="Submit a chat message and receive a completion",
)
# Handle incoming chat messages and route them to the interaction agent
async def chat_send(
    payload: ChatRequest,
) -> JSONResponse | PlainTextResponse:
    return await handle_chat_request(payload)


def _content_from_ui_message(message: dict[object, object]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content

    parts = message.get("parts")
    if isinstance(parts, list):
        part_items = cast(list[object], parts)
        text_parts: list[str] = []
        for part in part_items:
            if not isinstance(part, dict):
                continue
            part_data = cast(dict[object, object], part)
            if part_data.get("type") != "text":
                continue
            text = part_data.get("text")
            text_parts.append("" if text is None else str(text))
        return "".join(text_parts)
    return ""


async def _chat_request_from_stream_body(request: Request) -> ChatRequest:
    body = cast(object, await request.json())
    if not isinstance(body, dict):
        return ChatRequest(stream=True)

    body_data = cast(dict[object, object], body)
    raw_messages = body_data.get("messages")
    if not isinstance(raw_messages, list):
        return ChatRequest(stream=True)

    raw_message_items = cast(list[object], raw_messages)
    messages: list[ChatMessage] = []
    for item in raw_message_items:
        if not isinstance(item, dict):
            continue
        item_data = cast(dict[object, object], item)
        role = str(item_data.get("role") or "").strip()
        content = _content_from_ui_message(item_data)
        if role and content.strip():
            messages.append(ChatMessage(role=role, content=content))
    return ChatRequest(messages=messages, stream=True)


@router.post(
    "/stream",
    response_model=None,
    summary="Submit a chat message and stream a UI Message response",
)
async def chat_stream(request: Request) -> JSONResponse | StreamingResponse:
    try:
        payload = await _chat_request_from_stream_body(request)
    except Exception:
        return error_response("Invalid JSON", status_code=status.HTTP_400_BAD_REQUEST)

    user_message = next(
        (
            message
            for message in reversed(payload.messages)
            if message.role.lower().strip() == "user" and message.content.strip()
        ),
        None,
    )
    if user_message is None:
        return error_response(
            "Missing user message", status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        runtime = InteractionAgentRuntime()
    except ValueError as exc:
        logger.error("configuration error", extra={"error": str(exc)})
        return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

    return StreamingResponse(
        runtime.stream_execute(user_message.content.strip()),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "cache-control": "no-cache",
        },
    )


@router.get("/history", response_model=ChatHistoryResponse)
# Retrieve the conversation history from the log
def chat_history() -> ChatHistoryResponse:
    log = get_conversation_log()
    return ChatHistoryResponse(messages=log.to_chat_messages())


@router.delete("/history", response_model=ChatHistoryClearResponse)
def clear_history() -> ChatHistoryClearResponse:
    from ..services.execution import get_execution_agent_logs, get_execution_event_store

    # Clear conversation log
    log = get_conversation_log()
    log.clear()

    # Clear execution agent logs
    execution_logs = get_execution_agent_logs()
    execution_logs.clear_all()
    execution_events = get_execution_event_store()
    execution_events.clear_all()

    # Clear stored triggers
    trigger_service = get_trigger_service()
    trigger_service.clear_all()

    return ChatHistoryClearResponse()


__all__ = ["router"]
