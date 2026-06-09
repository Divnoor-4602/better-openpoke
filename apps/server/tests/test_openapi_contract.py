from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from server.app import app

EXPECTED_OPERATION_IDS = {
    ("delete", "/api/calendar/events/{event_id}"): "discard_calendar_event",
    ("delete", "/api/gmail/drafts/{draft_id}"): "discard_gmail_draft",
    ("delete", "/api/threads/{threadId}"): "delete_thread",
    ("get", "/api/admin/workspaces"): "list_workspaces",
    ("get", "/api/agent-runs"): "list_agent_runs",
    ("get", "/api/agent-runs/{requestId}"): "retrieve_agent_run",
    ("get", "/api/agent-runs/{requestId}/stream"): "stream_agent_run_events",
    ("get", "/api/health"): "retrieve_health",
    ("get", "/api/me"): "retrieve_me",
    ("get", "/api/meta/timezone"): "retrieve_timezone",
    ("get", "/api/reminders/events"): "stream_reminder_events",
    ("get", "/api/threads"): "list_threads",
    ("get", "/api/threads/{threadId}"): "retrieve_thread",
    ("get", "/api/threads/{threadId}/agent-runs"): "list_thread_agent_runs",
    ("get", "/api/threads/{threadId}/messages"): "list_thread_messages",
    ("patch", "/api/calendar/events/{event_id}"): "update_calendar_event",
    ("patch", "/api/gmail/drafts/{draft_id}"): "update_gmail_draft",
    ("patch", "/api/threads/{threadId}"): "update_thread",
    ("post", "/api/dev/reset"): "dev_reset",
    ("post", "/api/gmail/drafts/{draft_id}/send"): "send_gmail_draft",
    ("post", "/api/integrations/{provider}/connect"): "connect_integration",
    ("post", "/api/integrations/{provider}/disconnect"): "disconnect_integration",
    ("post", "/api/integrations/{provider}/status"): "retrieve_integration_status",
    ("post", "/api/meta/timezone"): "set_timezone",
    ("post", "/api/threads"): "create_thread",
    ("post", "/api/threads/{threadId}/agent-runs"): "create_thread_agent_run",
    ("post", "/api/threads/{threadId}/messages"): "create_thread_message",
    ("post", "/api/threads/{threadId}/messages/stream"): "stream_thread_message",
    ("post", "/api/threads/{threadId}/title"): "generate_thread_title",
}


def _schema() -> Mapping[str, object]:
    """Type the OpenAPI schema as a structural mapping.

    `FastAPI.openapi()` is typed as returning `dict[str, Any]` in the framework
    typeshed; we cast once at the boundary so each test reads typed values.
    """
    return cast(Mapping[str, object], cast(object, app.openapi()))


def _as_mapping(value: object) -> Mapping[str, object]:
    """Narrow `object` to a typed mapping (asserts at runtime)."""
    assert isinstance(value, Mapping), value
    return cast(Mapping[str, object], value)


def _operations(
    schema: Mapping[str, object],
) -> list[tuple[str, str, Mapping[str, object]]]:
    operations: list[tuple[str, str, Mapping[str, object]]] = []
    paths = _as_mapping(schema["paths"])
    for path, path_item in paths.items():
        item = _as_mapping(path_item)
        for method, operation in item.items():
            if method.lower() in {"get", "post", "patch", "delete", "put"}:
                operations.append((path, method, _as_mapping(operation)))
    return operations


def test_schema_exposes_only_unversioned_api_paths() -> None:
    schema = _schema()
    paths = set(_as_mapping(schema["paths"]))

    assert paths
    assert all(path.startswith("/api/") for path in paths)
    assert not any(path.startswith("/api/v1/") for path in paths)
    assert not any(path.startswith("/api/chat/") for path in paths)
    assert not any(path.startswith("/api/execution/") for path in paths)


def test_every_public_operation_has_stable_operation_id() -> None:
    schema = _schema()
    raw_operation_ids: list[object] = [
        operation.get("operationId") for _, _, operation in _operations(schema)
    ]

    assert all(isinstance(operation_id, str) and operation_id for operation_id in raw_operation_ids)
    operation_ids: list[str] = [op for op in raw_operation_ids if isinstance(op, str)]
    assert len(operation_ids) == len(set(operation_ids))
    assert all(" " not in operation_id for operation_id in operation_ids)


def test_public_operation_ids_match_sdk_contract() -> None:
    schema = _schema()
    actual = {
        (method, path): operation.get("operationId")
        for path, method, operation in _operations(schema)
    }

    assert actual == EXPECTED_OPERATION_IDS


def test_request_and_response_bodies_use_explicit_schemas() -> None:
    schema = _schema()
    for path, method, operation in _operations(schema):
        request_body = operation.get("requestBody")
        if isinstance(request_body, Mapping):
            request_body_map = cast(Mapping[str, object], request_body)
            content = _as_mapping(request_body_map.get("content") or {})
            for media in content.values():
                schema_obj = _as_mapping(_as_mapping(media).get("schema") or {})
                assert "$ref" in schema_obj, (method, path, schema_obj)

        responses = _as_mapping(operation.get("responses") or {})
        success_value = (
            responses.get("200") or responses.get("201") or responses.get("202")
        )
        assert isinstance(success_value, Mapping), (method, path)
        success = cast(Mapping[str, object], success_value)
        content = _as_mapping(success.get("content") or {})
        if "text/event-stream" in content:
            stream_schema = _as_mapping(
                _as_mapping(content["text/event-stream"])["schema"]
            )
            assert stream_schema["type"] == "string"
            continue
        json_media = _as_mapping(content.get("application/json") or {})
        json_schema = _as_mapping(json_media.get("schema") or {})
        assert "$ref" in json_schema, (method, path, json_schema)


def test_standard_error_response_is_documented_everywhere() -> None:
    schema = _schema()
    components = _as_mapping(schema["components"])
    schemas = _as_mapping(components["schemas"])
    error_schema = _as_mapping(schemas["ErrorResponse"])
    properties = _as_mapping(error_schema["properties"])
    assert {"ok", "error", "requestId"}.issubset(properties)

    for path, method, operation in _operations(schema):
        responses = _as_mapping(operation.get("responses") or {})
        for status_code in ("400", "404", "422", "500"):
            content = _as_mapping(_as_mapping(responses[status_code])["content"])
            json_schema = _as_mapping(_as_mapping(content["application/json"])["schema"])
            assert (
                json_schema["$ref"] == "#/components/schemas/ErrorResponse"
            ), (method, path, status_code)


def test_stream_routes_are_documented_as_event_streams() -> None:
    schema = _schema()
    paths = _as_mapping(schema["paths"])
    stream_paths = {path for path in paths if path.endswith("/stream")}
    assert stream_paths == {
        "/api/agent-runs/{requestId}/stream",
        "/api/threads/{threadId}/messages/stream",
    }

    for path in stream_paths:
        path_item = _as_mapping(paths[path])
        operation = _as_mapping(next(iter(path_item.values())))
        responses = _as_mapping(operation["responses"])
        success = _as_mapping(responses["200"])
        content = _as_mapping(success["content"])
        assert "text/event-stream" in content


def test_cursor_pagination_schema_is_consistent() -> None:
    schema = _schema()
    components = _as_mapping(schema["components"])
    schemas = _as_mapping(components["schemas"])
    cursor_page = _as_mapping(schemas["CursorPage"])
    properties = _as_mapping(cursor_page["properties"])
    assert {"nextCursor", "limit"}.issubset(properties)

    paginated_refs = {
        "#/components/schemas/ThreadListResponse",
        "#/components/schemas/MessageListResponse",
        "#/components/schemas/AgentRunListResponse",
    }
    discovered_refs: set[str] = set()
    for _, _, operation in _operations(schema):
        responses = _as_mapping(operation.get("responses") or {})
        for response in responses.values():
            if not isinstance(response, Mapping):
                continue
            response_map = cast(Mapping[str, object], response)
            content = _as_mapping(response_map.get("content") or {})
            json_media = _as_mapping(content.get("application/json") or {})
            json_schema = _as_mapping(json_media.get("schema") or {})
            ref = json_schema.get("$ref")
            if isinstance(ref, str) and ref in paginated_refs:
                discovered_refs.add(ref)
    assert discovered_refs == paginated_refs
