from __future__ import annotations

from fastapi.responses import JSONResponse

from ..config import Settings
from ..models.gmail import (
    GmailConnectPayload,
    GmailDisconnectPayload,
    GmailStatusPayload,
)
from ..services.gmail.client import disconnect_account, fetch_status, initiate_connect


def connect_gmail(payload: GmailConnectPayload, settings: Settings) -> JSONResponse:
    return initiate_connect(payload, settings)


def get_gmail_status(payload: GmailStatusPayload) -> JSONResponse:
    return fetch_status(payload)


def disconnect_gmail(payload: GmailDisconnectPayload) -> JSONResponse:
    return disconnect_account(payload)
