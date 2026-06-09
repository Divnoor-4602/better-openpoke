"""Shared test fixtures.

The workspace-isolation refactor gated every `/api/*` request behind HTTP
Basic auth and made store methods resolve `workspace_id` via a
`ContextVar` when not passed explicitly. These fixtures keep tests
ergonomic — set a default password, bind a default workspace for any test
that touches stores directly, and offer an authed `TestClient` factory.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Set the demo password before any server import — the lifespan check in
# `server.app` will otherwise refuse to import.
_ = os.environ.setdefault("DEMO_PASSWORD", "test-password")

DEFAULT_WORKSPACE_ID = "test_workspace"
DEFAULT_PASSWORD = os.environ["DEMO_PASSWORD"]


@pytest.fixture(autouse=True)
def _bind_test_workspace(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Bind a default workspace for every test, including async ones.

    Strategy: monkey-patch `require_current_workspace` for the duration of
    the test to return the default workspace when no value is set. This
    works for both sync tests (where the ContextVar binding propagates)
    and async tests using IsolatedAsyncioTestCase (where the test method
    runs in a new event loop with a fresh ContextVar that doesn't inherit
    the pytest setup context's binding).

    Real per-request behavior is still exercised via TestClient because
    the dep override below sets the ContextVar inside the request task.
    """
    from server.core import workspace_context

    def _stub_require() -> str:
        value = workspace_context.get_current_workspace()
        return value or DEFAULT_WORKSPACE_ID

    monkeypatch.setattr(
        workspace_context, "require_current_workspace", _stub_require
    )
    # Refresh references already imported by store modules so they pick up
    # the stub (modules captured the name at import time).
    from server.db import threads as _threads_mod
    from server.services.execution import event_store as _events_mod
    from server.services.memory import store as _memory_mod
    from server.services.triggers import store as _triggers_store
    from server.services.triggers import service as _triggers_svc
    from server.services import timezone_store as _tz_mod
    from server.services.conversation import log as _conv_mod
    from server.services.conversation.summarization import (
        working_memory_log as _wm_mod,
    )
    from server.services.execution import log_store as _exec_log_mod

    for mod in (
        _threads_mod,
        _events_mod,
        _memory_mod,
        _triggers_store,
        _triggers_svc,
        _tz_mod,
        _conv_mod,
        _wm_mod,
        _exec_log_mod,
    ):
        monkeypatch.setattr(mod, "require_current_workspace", _stub_require)
    yield


@pytest.fixture
def workspace_id() -> str:
    return DEFAULT_WORKSPACE_ID


@pytest.fixture
def auth() -> tuple[str, str]:
    return (DEFAULT_WORKSPACE_ID, DEFAULT_PASSWORD)


@pytest.fixture(autouse=True)
def _override_workspace_dep() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Skip Basic auth in tests by overriding the workspace dependency.

    The override sets the ContextVar to the default test workspace,
    matching what `get_workspace_id` would do on a real authed request.
    """
    from server.api.dependencies import get_workspace_id
    from server.app import app
    from server.core.workspace_context import set_current_workspace

    async def _stub_get_workspace_id() -> str:
        set_current_workspace(DEFAULT_WORKSPACE_ID)
        return DEFAULT_WORKSPACE_ID

    app.dependency_overrides[get_workspace_id] = _stub_get_workspace_id
    try:
        yield
    finally:
        _ = app.dependency_overrides.pop(get_workspace_id, None)


@pytest.fixture
def client(auth: tuple[str, str]):
    """A TestClient pre-configured with default Basic auth headers.

    Auth is also covered by `_override_workspace_dep`, but having Basic
    creds set means tests that hit `_security` directly (or measure
    headers) behave like real requests.
    """
    from fastapi.testclient import TestClient

    from server.app import app

    test_client = TestClient(app)
    test_client.auth = auth
    return test_client
