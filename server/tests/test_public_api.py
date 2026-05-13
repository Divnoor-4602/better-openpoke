from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server.api.routes import threads as thread_routes
from server.app import app
from server.db.threads import ThreadRepository, get_thread_repository
from server.services.execution.event_store import ExecutionEventStore

_MISSING = object()


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
            app.dependency_overrides.pop(get_thread_repository, None)
        else:
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
    data = response.json()
    thread_id = data["thread"]["threadId"]
    assert data["thread"]["title"] == thread_id
    return thread_id


def test_thread_crud_and_message_history(client: TestClient) -> None:
    thread_id = _create_thread(client)

    update = client.patch(f"/api/threads/{thread_id}", json={"title": "Inbox work"})
    assert update.status_code == 200
    assert update.json()["thread"]["title"] == "Inbox work"

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
    assert created_message.json()["message"]["content"] == "Check my mail"

    history = client.get(f"/api/threads/{thread_id}/messages")
    assert history.status_code == 200
    assert [item["content"] for item in history.json()["items"]] == ["Check my mail"]

    deleted = client.delete(f"/api/threads/{thread_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_message_stream_submission_records_user_message(client: TestClient) -> None:
    thread_id = _create_thread(client)

    class FakeRuntime:
        def stream_execute(self, user_message: str) -> Iterator[str]:
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

    history = client.get(f"/api/threads/{thread_id}/messages").json()
    assert history["items"][0]["content"] == "Stream this"


def test_agent_runs_global_and_thread_scoped(
    client: TestClient, execution_store: ExecutionEventStore
) -> None:
    thread_id = _create_thread(client)

    with patch("server.services.execution.get_execution_event_store", return_value=execution_store), patch(
        "server.api.routes.agent_runs.get_execution_event_store",
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
        assert created.json()["run"]["threadId"] == thread_id

        execution_store.record_submitted(
            request_id="req-global",
            memory_id="mem-global",
            title="Global",
            instructions="Global work",
        )

        scoped = client.get(f"/api/threads/{thread_id}/agent-runs")
        assert scoped.status_code == 200
        assert [item["requestId"] for item in scoped.json()["items"]] == ["req-thread"]

        global_runs = client.get("/api/agent-runs")
        assert global_runs.status_code == 200
        assert {item["requestId"] for item in global_runs.json()["items"]} == {
            "req-thread",
            "req-global",
        }


def test_integration_routes_use_generic_gmail_provider(client: TestClient) -> None:
    def connect(_: object, __: object) -> Any:
        return _json_response(
            {
                "ok": True,
                "redirect_url": "https://example.test/oauth",
                "connection_request_id": "conn-req",
                "user_id": "user-1",
            }
        )

    def status(_: object) -> Any:
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

    def disconnect(_: object) -> Any:
        return _json_response(
            {
                "ok": True,
                "disconnected": True,
                "removed_connection_ids": ["conn-1"],
            }
        )

    with patch("server.api.routes.integrations.connect_gmail", connect), patch(
        "server.api.routes.integrations.get_gmail_status",
        status,
    ), patch("server.api.routes.integrations.disconnect_gmail", disconnect):
        connected = client.post(
            "/api/integrations/gmail/connect",
            json={"userId": "user-1", "authConfigId": "auth-1"},
        )
        assert connected.status_code == 200
        assert connected.json()["connectionRequestId"] == "conn-req"

        current = client.post(
            "/api/integrations/gmail/status",
            json={"userId": "user-1"},
        )
        assert current.status_code == 200
        assert current.json()["connected"] is True

        removed = client.post(
            "/api/integrations/gmail/disconnect",
            json={"connectionId": "conn-1"},
        )
        assert removed.status_code == 200
        assert removed.json()["removedConnectionIds"] == ["conn-1"]


def _json_response(payload: dict[str, Any]) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(payload)
