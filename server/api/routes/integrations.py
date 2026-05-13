from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ...config import Settings, get_settings
from ...core.errors import ERROR_RESPONSES
from ...integrations.gmail import connect_gmail, disconnect_gmail, get_gmail_status
from ...models.gmail import GmailConnectPayload, GmailDisconnectPayload, GmailStatusPayload
from ..schemas import (
    IntegrationConnectRequest,
    IntegrationConnectResponse,
    IntegrationDisconnectRequest,
    IntegrationDisconnectResponse,
    IntegrationStatusRequest,
    IntegrationStatusResponse,
    Provider,
)

router = APIRouter(
    prefix="/integrations/{provider}",
    tags=["integrations"],
    responses=ERROR_RESPONSES,
)


@router.post(
    "/connect",
    response_model=IntegrationConnectResponse,
    operation_id="connect_integration",
    summary="Connect an integration provider",
)
def connect_integration(
    provider: Provider,
    payload: IntegrationConnectRequest,
    settings: Settings = Depends(get_settings),
) -> IntegrationConnectResponse:
    _assert_provider(provider)
    response = connect_gmail(
        GmailConnectPayload(
            user_id=payload.userId,
            auth_config_id=payload.authConfigId,
        ),
        settings,
    )
    data = _ok_payload(response)
    return IntegrationConnectResponse(
        ok=True,
        redirectUrl=_optional_str(data.get("redirect_url")),
        connectionRequestId=_optional_str(data.get("connection_request_id")),
        userId=_optional_str(data.get("user_id")),
    )


@router.post(
    "/status",
    response_model=IntegrationStatusResponse,
    operation_id="retrieve_integration_status",
    summary="Get integration status",
)
def retrieve_integration_status(
    provider: Provider,
    payload: IntegrationStatusRequest,
) -> IntegrationStatusResponse:
    _assert_provider(provider)
    response = get_gmail_status(
        GmailStatusPayload(
            user_id=payload.userId,
            connection_request_id=payload.connectionRequestId,
        )
    )
    data = _ok_payload(response)
    profile = data.get("profile")
    return IntegrationStatusResponse(
        ok=True,
        connected=bool(data.get("connected")),
        status=str(data.get("status") or "UNKNOWN"),
        email=_optional_str(data.get("email")),
        userId=_optional_str(data.get("user_id")),
        profile=profile if isinstance(profile, dict) else None,
        profileSource=str(data.get("profile_source") or "none"),
    )


@router.post(
    "/disconnect",
    response_model=IntegrationDisconnectResponse,
    operation_id="disconnect_integration",
    summary="Disconnect an integration provider",
)
def disconnect_integration(
    provider: Provider,
    payload: IntegrationDisconnectRequest,
) -> IntegrationDisconnectResponse:
    _assert_provider(provider)
    response = disconnect_gmail(
        GmailDisconnectPayload(
            user_id=payload.userId,
            connection_id=payload.connectionId,
            connection_request_id=payload.connectionRequestId,
        )
    )
    data = _ok_payload(response)
    removed = data.get("removed_connection_ids")
    warnings = data.get("warnings")
    return IntegrationDisconnectResponse(
        ok=True,
        disconnected=bool(data.get("disconnected")),
        removedConnectionIds=removed if isinstance(removed, list) else [],
        message=_optional_str(data.get("message")),
        warnings=warnings if isinstance(warnings, list) else [],
    )


def _assert_provider(provider: Provider) -> None:
    if provider != "gmail":  # pragma: no cover - Literal validation handles this
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration provider not found")


def _ok_payload(response: JSONResponse) -> dict[str, Any]:
    data = json.loads(response.body.decode("utf-8"))
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid provider response")
    if response.status_code >= 400 or data.get("ok") is False:
        raise HTTPException(
            status_code=response.status_code,
            detail=data.get("detail") or data.get("error") or "Integration request failed",
        )
    return data


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
