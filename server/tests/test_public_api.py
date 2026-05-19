from __future__ import annotations

import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from server.api.routes import threads as thread_routes
from server.app import app
from server.db.threads import ThreadRepository, get_thread_repository
from server.services.execution.event_store import ExecutionEventStore

_MISSING = object()


def _json(response: object) -> Mapping[str, object]:
    """Type the result of TestClient response.json() as a mapping."""
    decoded = cast(object, getattr(response, "json")())
    assert isinstance(decoded, Mapping), decoded
    return cast(Mapping[str, object], decoded)


def _as_mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping), value
    return cast(Mapping[str, object], value)


def _items(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    items = payload["items"]
    assert isinstance(items, list)
    return [_as_mapping(item) for item in cast(list[object], items)]


@pytest.fixture()
def client() -> Iterator[TestClient]:
    tmpdir = tempfile.TemporaryDirectory()
    repository = ThreadRepository(Path(tmpdir.name) / "threads.db")
    previous_override = app.dependency_overrides.get(get_thread_repository, _MISSING)
    app.dependency_overrides[get_thread_repository] = lambda: repository
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        if previous_override is _MISSING:
            _ = app.dependency_overrides.pop(get_thread_repository, None)
        else:
            assert callable(previous_override)
            app.dependency_overrides[get_thread_repository] = previous_override
        tmpdir.cleanup()


@pytest.fixture()
def execution_store() -> Iterator[ExecutionEventStore]:
    tmpdir: TemporaryDirectory[str] = tempfile.TemporaryDirectory()
    try:
        yield ExecutionEventStore(Path(tmpdir.name) / "execution_events.db")
    finally:
        tmpdir.cleanup()


def _create_thread(client: TestClient) -> str:
    response = client.post("/api/threads")
    assert response.status_code == 201
    data = _json(response)
    thread = _as_mapping(data["thread"])
    thread_id = thread["threadId"]
    assert isinstance(thread_id, str)
    assert thread["title"] is None
    return thread_id


def test_thread_crud_and_message_history(client: TestClient) -> None:
    thread_id = _create_thread(client)

    update = client.patch(f"/api/threads/{thread_id}", json={"title": "Inbox work"})
    assert update.status_code == 200
    assert _as_mapping(_json(update)["thread"])["title"] == "Inbox work"

    created_message = client.post(
        f"/api/threads/{thread_id}/messages",
        json={
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Check my mail"}],
            }
        },
    )
    assert created_message.status_code == 201
    assert _as_mapping(_json(created_message)["message"])["content"] == "Check my mail"

    history = client.get(f"/api/threads/{thread_id}/messages")
    assert history.status_code == 200
    assert [item["content"] for item in _items(_json(history))] == ["Check my mail"]

    deleted = client.delete(f"/api/threads/{thread_id}")
    assert deleted.status_code == 200
    assert _json(deleted)["ok"] is True


def test_generate_thread_title_updates_thread(client: TestClient) -> None:
    thread_id = _create_thread(client)
    for content in ("Plan my launch", "What should I prioritize?", "Focus the scope"):
        response = client.post(
            f"/api/threads/{thread_id}/messages",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": content}],
                }
            },
        )
        assert response.status_code == 201

    async def fake_generate_title(thread_id_arg: str, *, repository: ThreadRepository) -> str:
        assert thread_id_arg == thread_id
        _ = repository.update_thread(thread_id_arg, title="Launch Planning")
        return "Launch Planning"

    with patch.object(thread_routes, "generate_title_for_thread", fake_generate_title):
        generated = client.post(f"/api/threads/{thread_id}/title")

    assert generated.status_code == 200
    assert _as_mapping(_json(generated)["thread"])["title"] == "Launch Planning"


def test_message_stream_submission_records_user_message(client: TestClient) -> None:
    thread_id = _create_thread(client)

    class FakeRuntime:
        async def stream_execute(
            self, user_message: str, *args: object, **kwargs: object
        ):
            _ = args
            _ = kwargs
            yield f'data: {{"type":"text-delta","id":"t","delta":"{user_message}"}}\n\n'

    with patch.object(thread_routes, "InteractionAgentRuntime", return_value=FakeRuntime()):
        response = client.post(
            f"/api/threads/{thread_id}/messages/stream",
            json={
                "messages": [
                    {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Stream this"}],
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "Stream this" in response.text

    history = _json(client.get(f"/api/threads/{thread_id}/messages"))
    assert _items(history)[0]["content"] == "Stream this"


def test_agent_runs_global_and_thread_scoped(
    client: TestClient, execution_store: ExecutionEventStore
) -> None:
    thread_id = _create_thread(client)

    with patch(
        "server.services.execution.get_execution_event_store",
        return_value=execution_store,
    ), patch(
        "server.api.routes.agent_runs.get_execution_event_store",
        return_value=execution_store,
    ), patch(
        "server.api.routes.threads.get_execution_event_store",
        return_value=execution_store,
    ):
        created = client.post(
            f"/api/threads/{thread_id}/agent-runs",
            json={
                "requestId": "req-thread",
                "memoryId": "mem-thread",
                "instructions": "Do work",
            },
        )
        assert created.status_code == 202
        assert _as_mapping(_json(created)["run"])["threadId"] == thread_id

        execution_store.record_submitted(
            request_id="req-global",
            memory_id="mem-global",
            title="Global",
            instructions="Global work",
        )

        scoped = client.get(f"/api/threads/{thread_id}/agent-runs")
        assert scoped.status_code == 200
        assert [item["requestId"] for item in _items(_json(scoped))] == ["req-thread"]

        global_runs = client.get("/api/agent-runs")
        assert global_runs.status_code == 200
        assert {item["requestId"] for item in _items(_json(global_runs))} == {
            "req-thread",
            "req-global",
        }


def test_integration_routes_use_generic_gmail_provider(client: TestClient) -> None:
    def connect(_payload: object, _settings: object) -> JSONResponse:
        return _json_response(
            {
                "ok": True,
                "redirect_url": "https://example.test/oauth",
                "connection_request_id": "conn-req",
                "user_id": "user-1",
            }
        )

    def status(_payload: object) -> JSONResponse:
        return _json_response(
            {
                "ok": True,
                "connected": True,
                "status": "ACTIVE",
                "email": "user@example.test",
                "user_id": "user-1",
                "profile": {"email": "user@example.test"},
                "profile_source": "cache",
            }
        )

    def disconnect(_payload: object) -> JSONResponse:
        return _json_response(
            {
                "ok": True,
                "disconnected": True,
                "removed_connection_ids": ["conn-1"],
            }
        )

    with patch("server.api.routes.integrations.connect_google", connect), patch(
        "server.api.routes.integrations.get_google_status",
        status,
    ), patch("server.api.routes.integrations.disconnect_google", disconnect):
        connected = client.post(
            "/api/integrations/google/connect",
            json={"userId": "user-1", "authConfigId": "auth-1"},
        )
        assert connected.status_code == 200
        assert _json(connected)["connectionRequestId"] == "conn-req"

        current = client.post(
            "/api/integrations/google/status",
            json={"userId": "user-1"},
        )
        assert current.status_code == 200
        assert _json(current)["connected"] is True

        removed = client.post(
            "/api/integrations/google/disconnect",
            json={"connectionId": "conn-1"},
        )
        assert removed.status_code == 200
        assert _json(removed)["removedConnectionIds"] == ["conn-1"]


def _json_response(payload: dict[str, object]) -> JSONResponse:
    return JSONResponse(payload)
