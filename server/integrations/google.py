from __future__ import annotations

import json
from typing import cast

from fastapi.responses import JSONResponse

from ..config import Settings
from ..models.google import (
    GoogleConnectPayload,
    GoogleDisconnectPayload,
    GoogleStatusPayload,
)
from ..services.gmail.client import disconnect_account, fetch_status, initiate_connect
from ..services.gmail.connections import register_workspace, unregister_workspace


def connect_google(payload: GoogleConnectPayload, settings: Settings) -> JSONResponse:
    # OAuth hasn't completed yet — we only have a redirect URL at this
    # point. Registration happens in `get_google_status` once the
    # connection actually reports ACTIVE, so the importance watcher
    # doesn't start polling a not-yet-connected workspace.
    return initiate_connect(payload, settings)


def get_google_status(payload: GoogleStatusPayload) -> JSONResponse:
    response = fetch_status(payload)
    if payload.user_id and response.status_code < 400:
        try:
            data = cast(object, json.loads(bytes(response.body).decode("utf-8")))
        except Exception:
            data = None
        if isinstance(data, dict):
            data_map = cast(dict[str, object], data)
            if data_map.get("connected") and data_map.get("status") == "ACTIVE":
                register_workspace(payload.user_id)
    return response


def disconnect_google(payload: GoogleDisconnectPayload) -> JSONResponse:
    response = disconnect_account(payload)
    if payload.user_id and response.status_code < 400:
        unregister_workspace(payload.user_id)
    return response
