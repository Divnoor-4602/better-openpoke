"""Vercel AI SDK UI Message Stream helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Literal, TypeAlias, TypedDict, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class StartMessagePart(TypedDict):
    type: Literal["start"]
    messageId: str


class StartStepPart(TypedDict):
    type: Literal["start-step"]


class FinishStepPart(TypedDict):
    type: Literal["finish-step"]


class FinishMessagePart(TypedDict):
    type: Literal["finish"]


class TextStartPart(TypedDict):
    type: Literal["text-start"]
    id: str


class TextDeltaPart(TypedDict):
    type: Literal["text-delta"]
    id: str
    delta: str


class TextEndPart(TypedDict):
    type: Literal["text-end"]
    id: str


class ReasoningStartPart(TypedDict):
    type: Literal["reasoning-start"]
    id: str


class ReasoningDeltaPart(TypedDict):
    type: Literal["reasoning-delta"]
    id: str
    delta: str


class ReasoningEndPart(TypedDict):
    type: Literal["reasoning-end"]
    id: str


class ToolInputStartPart(TypedDict):
    type: Literal["tool-input-start"]
    toolCallId: str
    toolName: str


class ToolInputDeltaPart(TypedDict):
    type: Literal["tool-input-delta"]
    toolCallId: str
    inputTextDelta: str


class ToolInputAvailablePart(TypedDict):
    type: Literal["tool-input-available"]
    toolCallId: str
    toolName: str
    input: JsonValue


class ToolOutputAvailablePart(TypedDict):
    type: Literal["tool-output-available"]
    toolCallId: str
    output: JsonValue


class DataExecutionEventPart(TypedDict):
    type: Literal["data-execution-event"]
    data: JsonValue


class ErrorPart(TypedDict):
    type: Literal["error"]
    errorText: str


UiStreamPart: TypeAlias = (
    StartMessagePart
    | StartStepPart
    | FinishStepPart
    | FinishMessagePart
    | TextStartPart
    | TextDeltaPart
    | TextEndPart
    | ReasoningStartPart
    | ReasoningDeltaPart
    | ReasoningEndPart
    | ToolInputStartPart
    | ToolInputDeltaPart
    | ToolInputAvailablePart
    | ToolOutputAvailablePart
    | DataExecutionEventPart
    | ErrorPart
)


def sse_part(part: UiStreamPart) -> str:
    return f"data: {json.dumps(part, ensure_ascii=False, default=str)}\n\n"


def start_message(message_id: str) -> StartMessagePart:
    return {"type": "start", "messageId": message_id}


def start_step() -> StartStepPart:
    return {"type": "start-step"}


def finish_step() -> FinishStepPart:
    return {"type": "finish-step"}


def finish_message() -> FinishMessagePart:
    return {"type": "finish"}


def text_start(part_id: str) -> TextStartPart:
    return {"type": "text-start", "id": part_id}


def text_delta(part_id: str, delta: str) -> TextDeltaPart:
    return {"type": "text-delta", "id": part_id, "delta": delta}


def text_end(part_id: str) -> TextEndPart:
    return {"type": "text-end", "id": part_id}


def reasoning_start(part_id: str) -> ReasoningStartPart:
    return {"type": "reasoning-start", "id": part_id}


def reasoning_delta(part_id: str, delta: str) -> ReasoningDeltaPart:
    return {"type": "reasoning-delta", "id": part_id, "delta": delta}


def reasoning_end(part_id: str) -> ReasoningEndPart:
    return {"type": "reasoning-end", "id": part_id}


def tool_input_start(tool_call_id: str, tool_name: str) -> ToolInputStartPart:
    return {
        "type": "tool-input-start",
        "toolCallId": tool_call_id,
        "toolName": tool_name,
    }


def tool_input_delta(tool_call_id: str, input_text_delta: str) -> ToolInputDeltaPart:
    return {
        "type": "tool-input-delta",
        "toolCallId": tool_call_id,
        "inputTextDelta": input_text_delta,
    }


def tool_input_available(
    tool_call_id: str, tool_name: str, input_payload: JsonValue
) -> ToolInputAvailablePart:
    return {
        "type": "tool-input-available",
        "toolCallId": tool_call_id,
        "toolName": tool_name,
        "input": input_payload,
    }


def tool_output_available(
    tool_call_id: str, output: JsonValue
) -> ToolOutputAvailablePart:
    return {
        "type": "tool-output-available",
        "toolCallId": tool_call_id,
        "output": output,
    }


def data_execution_event(payload: Mapping[str, object]) -> DataExecutionEventPart:
    return {
        "type": "data-execution-event",
        "data": _json_object(cast(Mapping[object, object], payload)),
    }


def error_part(error_text: str) -> ErrorPart:
    return {"type": "error", "errorText": error_text}


DONE = "data: [DONE]\n\n"


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


__all__ = [
    "DONE",
    "DataExecutionEventPart",
    "ErrorPart",
    "FinishMessagePart",
    "FinishStepPart",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "ReasoningDeltaPart",
    "ReasoningEndPart",
    "ReasoningStartPart",
    "StartMessagePart",
    "StartStepPart",
    "TextDeltaPart",
    "TextEndPart",
    "TextStartPart",
    "ToolInputAvailablePart",
    "ToolInputDeltaPart",
    "ToolInputStartPart",
    "ToolOutputAvailablePart",
    "UiStreamPart",
    "data_execution_event",
    "error_part",
    "finish_message",
    "finish_step",
    "reasoning_delta",
    "reasoning_end",
    "reasoning_start",
    "sse_part",
    "start_message",
    "start_step",
    "text_delta",
    "text_end",
    "text_start",
    "tool_input_available",
    "tool_input_delta",
    "tool_input_start",
    "tool_output_available",
]
