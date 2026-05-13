from __future__ import annotations

from typing import Any

from server.app import app

EXPECTED_OPERATION_IDS = {
    ("get", "/api/health"): "retrieve_health",
    ("get", "/api/threads"): "list_threads",
    ("post", "/api/threads"): "create_thread",
    ("get", "/api/threads/{threadId}"): "retrieve_thread",
    ("patch", "/api/threads/{threadId}"): "update_thread",
    ("delete", "/api/threads/{threadId}"): "delete_thread",
    ("get", "/api/threads/{threadId}/messages"): "list_thread_messages",
    ("post", "/api/threads/{threadId}/messages"): "create_thread_message",
    ("post", "/api/threads/{threadId}/messages/stream"): "stream_thread_message",
    ("get", "/api/threads/{threadId}/agent-runs"): "list_thread_agent_runs",
    ("post", "/api/threads/{threadId}/agent-runs"): "create_thread_agent_run",
    ("get", "/api/agent-runs"): "list_agent_runs",
    ("get", "/api/agent-runs/{requestId}"): "retrieve_agent_run",
    ("get", "/api/agent-runs/{requestId}/stream"): "stream_agent_run_events",
    ("post", "/api/integrations/{provider}/connect"): "connect_integration",
    ("post", "/api/integrations/{provider}/status"): "retrieve_integration_status",
    ("post", "/api/integrations/{provider}/disconnect"): "disconnect_integration",
}


def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "patch", "delete", "put"}:
                operations.append((path, method, operation))
    return operations


def test_schema_exposes_only_unversioned_api_paths() -> None:
    schema = app.openapi()
    paths = set(schema["paths"])

    assert paths
    assert all(path.startswith("/api/") for path in paths)
    assert not any(path.startswith("/api/v1/") for path in paths)
    assert not any(path.startswith("/api/chat/") for path in paths)
    assert not any(path.startswith("/api/execution/") for path in paths)


def test_every_public_operation_has_stable_operation_id() -> None:
    schema = app.openapi()
    operation_ids = [
        operation.get("operationId") for _, _, operation in _operations(schema)
    ]

    assert all(isinstance(operation_id, str) and operation_id for operation_id in operation_ids)
    assert len(operation_ids) == len(set(operation_ids))
    assert all(" " not in operation_id for operation_id in operation_ids)


def test_public_operation_ids_match_sdk_contract() -> None:
    schema = app.openapi()
    actual = {
        (method, path): operation.get("operationId")
        for path, method, operation in _operations(schema)
    }

    assert actual == EXPECTED_OPERATION_IDS


def test_request_and_response_bodies_use_explicit_schemas() -> None:
    schema = app.openapi()
    for path, method, operation in _operations(schema):
        request_body = operation.get("requestBody")
        if isinstance(request_body, dict):
            content = request_body.get("content", {})
            for media in content.values():
                schema_obj = media.get("schema", {})
                assert "$ref" in schema_obj, (method, path, schema_obj)

        responses = operation.get("responses", {})
        success = responses.get("200") or responses.get("201") or responses.get("202")
        assert isinstance(success, dict), (method, path)
        content = success.get("content", {})
        if "text/event-stream" in content:
            assert content["text/event-stream"]["schema"]["type"] == "string"
            continue
        json_schema = content.get("application/json", {}).get("schema", {})
        assert "$ref" in json_schema, (method, path, json_schema)


def test_standard_error_response_is_documented_everywhere() -> None:
    schema = app.openapi()
    error_schema = schema["components"]["schemas"]["ErrorResponse"]
    assert set(["ok", "error", "requestId"]).issubset(error_schema["properties"])

    for path, method, operation in _operations(schema):
        responses = operation.get("responses", {})
        for status_code in ("400", "404", "422", "500"):
            content = responses[status_code]["content"]
            assert (
                content["application/json"]["schema"]["$ref"]
                == "#/components/schemas/ErrorResponse"
            ), (method, path, status_code)


def test_stream_routes_are_documented_as_event_streams() -> None:
    schema = app.openapi()
    stream_paths = {
        path
        for path in schema["paths"]
        if path.endswith("/stream")
    }
    assert stream_paths == {
        "/api/agent-runs/{requestId}/stream",
        "/api/threads/{threadId}/messages/stream",
    }

    for path in stream_paths:
        operation = next(iter(schema["paths"][path].values()))
        assert "text/event-stream" in operation["responses"]["200"]["content"]


def test_cursor_pagination_schema_is_consistent() -> None:
    schema = app.openapi()
    cursor_page = schema["components"]["schemas"]["CursorPage"]
    assert set(["nextCursor", "limit"]).issubset(cursor_page["properties"])

    paginated_refs = {
        "#/components/schemas/ThreadListResponse",
        "#/components/schemas/MessageListResponse",
        "#/components/schemas/AgentRunListResponse",
    }
    discovered_refs: set[str] = set()
    for _, _, operation in _operations(schema):
        for response in operation.get("responses", {}).values():
            content = response.get("content", {}) if isinstance(response, dict) else {}
            ref = content.get("application/json", {}).get("schema", {}).get("$ref")
            if ref in paginated_refs:
                discovered_refs.add(ref)
    assert discovered_refs == paginated_refs
