from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Literal, NotRequired, TypeAlias, TypedDict, cast

import httpx

from ..config import get_settings

OpenRouterBaseURL = "https://openrouter.ai/api/v1"

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
OpenRouterRole: TypeAlias = Literal["system", "user", "assistant", "tool"]


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter API returns an error response."""


class OpenRouterMessage(TypedDict):
    role: OpenRouterRole
    content: str
    tool_call_id: NotRequired[str]
    name: NotRequired[str]
    tool_calls: NotRequired[list["OpenRouterToolCall"]]


class OpenRouterFunctionDescription(TypedDict):
    name: str
    parameters: JsonObject
    description: NotRequired[str]


class OpenRouterTool(TypedDict):
    type: Literal["function"]
    function: OpenRouterFunctionDescription


class OpenRouterFunctionCall(TypedDict):
    name: str
    arguments: str


class OpenRouterToolCall(TypedDict):
    id: str
    type: Literal["function"]
    function: OpenRouterFunctionCall


class OpenRouterToolCallDelta(TypedDict, total=False):
    index: int
    id: str
    type: Literal["function"]
    function: OpenRouterFunctionCall


class OpenRouterAssistantMessage(TypedDict):
    role: str
    content: str | None
    tool_calls: NotRequired[list[OpenRouterToolCall]]


class OpenRouterStreamingDelta(TypedDict, total=False):
    role: str
    content: str | None
    tool_calls: list[OpenRouterToolCallDelta]


class OpenRouterNonStreamingChoice(TypedDict):
    finish_reason: str | None
    native_finish_reason: NotRequired[str | None]
    message: OpenRouterAssistantMessage


class OpenRouterStreamingChoice(TypedDict):
    finish_reason: str | None
    native_finish_reason: NotRequired[str | None]
    delta: OpenRouterStreamingDelta


class OpenRouterChatCompletion(TypedDict):
    id: str
    choices: list[OpenRouterNonStreamingChoice]
    created: int
    model: str
    object: Literal["chat.completion"]


class OpenRouterChatCompletionChunk(TypedDict):
    id: str
    choices: list[OpenRouterStreamingChoice]
    created: int
    model: str
    object: Literal["chat.completion.chunk"]


def _headers(*, api_key: str | None = None) -> dict[str, str]:
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterError("Missing OpenRouter API key")

    headers: dict[str, str] = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    return headers


def _build_messages(
    messages: Sequence[Mapping[str, str]], system: str | None
) -> list[OpenRouterMessage]:
    openrouter_messages: list[OpenRouterMessage] = []
    for message in messages:
        role = _coerce_role(message.get("role"))
        if role is None:
            continue
        openrouter_messages.append(
            OpenRouterMessage(role=role, content=message.get("content") or "")
        )
    if system:
        return [OpenRouterMessage(role="system", content=system), *openrouter_messages]
    return openrouter_messages


def _coerce_role(role: str | None) -> OpenRouterRole | None:
    if role in {"system", "user", "assistant", "tool"}:
        return cast(OpenRouterRole, role)
    return None


def _handle_response_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    detail: str
    try:
        payload = _response_json_object(response)
        raw_detail = payload.get("error") or payload.get("message")
        detail = str(raw_detail) if raw_detail else json.dumps(payload)
    except Exception:
        detail = response.text
    raise OpenRouterError(
        f"OpenRouter request failed ({response.status_code}): {detail}"
    ) from exc


def _response_json_object(response: httpx.Response) -> JsonObject:
    payload = cast(object, response.json())
    if not isinstance(payload, dict):
        raise OpenRouterError("OpenRouter response was not a JSON object")
    return _json_object(cast(Mapping[object, object], payload))


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return _json_object(cast(Mapping[object, object], value))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in value]
    return str(value)


def _json_object(payload: Mapping[object, object]) -> JsonObject:
    return {str(key): _json_value(value) for key, value in payload.items()}


async def request_chat_completion(
    *,
    model: str,
    messages: Sequence[Mapping[str, str]],
    system: str | None = None,
    api_key: str | None = None,
    tools: Sequence[Mapping[str, object]] | None = None,
    base_url: str = OpenRouterBaseURL,
) -> OpenRouterChatCompletion:
    """Request a chat completion and return the raw JSON payload."""

    payload: dict[str, object] = {
        "model": model,
        "messages": _build_messages(messages, system),
        "stream": False,
    }
    if tools:
        payload["tools"] = [
            _json_object(cast(Mapping[object, object], tool)) for tool in tools
        ]

    url = f"{base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                headers=_headers(api_key=api_key),
                json=payload,
                timeout=60.0,  # Set reasonable timeout instead of None
            )
            try:
                _ = response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _handle_response_error(exc)
            return cast(
                OpenRouterChatCompletion,
                cast(object, _response_json_object(response)),
            )
        except httpx.HTTPStatusError as exc:  # pragma: no cover - handled above
            _handle_response_error(exc)
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

    raise OpenRouterError("OpenRouter request failed: unknown error")


async def stream_chat_completion(
    *,
    model: str,
    messages: Sequence[Mapping[str, str]],
    system: str | None = None,
    api_key: str | None = None,
    tools: Sequence[Mapping[str, object]] | None = None,
    base_url: str = OpenRouterBaseURL,
) -> AsyncIterator[OpenRouterChatCompletionChunk]:
    """Stream OpenAI-compatible chat completion chunks from OpenRouter."""

    payload: dict[str, object] = {
        "model": model,
        "messages": _build_messages(messages, system),
        "stream": True,
    }
    if tools:
        payload["tools"] = [
            _json_object(cast(Mapping[object, object], tool)) for tool in tools
        ]

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {**_headers(api_key=api_key), "Accept": "text/event-stream"}

    timeout = httpx.Timeout(connect=300.0, write=300.0, read=None, pool=300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                try:
                    _ = response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    _handle_response_error(exc)

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = cast(object, json.loads(data))
                    except json.JSONDecodeError as exc:
                        raise OpenRouterError(
                            f"OpenRouter stream emitted invalid JSON: {exc}"
                        ) from exc
                    if not isinstance(chunk, dict):
                        raise OpenRouterError(
                            "OpenRouter stream emitted a non-object JSON chunk"
                        )
                    yield cast(
                        OpenRouterChatCompletionChunk,
                        cast(
                            object,
                            _json_object(cast(Mapping[object, object], chunk)),
                        ),
                    )
        except httpx.HTTPStatusError as exc:  # pragma: no cover - handled above
            _handle_response_error(exc)
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter stream failed: {exc}") from exc


__all__ = [
    "OpenRouterError",
    "OpenRouterAssistantMessage",
    "OpenRouterChatCompletion",
    "OpenRouterChatCompletionChunk",
    "OpenRouterBaseURL",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "OpenRouterMessage",
    "OpenRouterTool",
    "OpenRouterToolCall",
    "request_chat_completion",
    "stream_chat_completion",
]
