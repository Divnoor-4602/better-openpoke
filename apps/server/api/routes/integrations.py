from __future__ import annotations

import json
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ...config import Settings, get_settings
from ...core.errors import ERROR_RESPONSES
from ...core.workspace_context import require_current_workspace
from ...integrations.google import connect_google, disconnect_google, get_google_status
from ...models.google import (
    GoogleConnectPayload,
    GoogleDisconnectPayload,
    GoogleStatusPayload,
)
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
    settings: Annotated[Settings, Depends(get_settings)],
) -> IntegrationConnectResponse:
    _assert_provider(provider)
    # Always scope Composio connection to the caller's workspace, even if the
    # client supplied a userId — testers can't impersonate each other's Gmail.
    workspace_id = require_current_workspace()
    auth_config_id = payload.authConfigId or settings.composio_google_auth_config_id
    response = connect_google(
        GoogleConnectPayload(
            user_id=workspace_id,
            auth_config_id=auth_config_id,
            return_to=payload.returnTo,
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
    workspace_id = require_current_workspace()
    response = get_google_status(
        GoogleStatusPayload(
            user_id=workspace_id,
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
        profile=cast(dict[str, object], profile) if isinstance(profile, dict) else None,
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
    workspace_id = require_current_workspace()
    response = disconnect_google(
        GoogleDisconnectPayload(
            user_id=workspace_id,
            connection_id=payload.connectionId,
            connection_request_id=payload.connectionRequestId,
        )
    )
    data = _ok_payload(response)
    removed = data.get("removed_connection_ids")
    warnings = data.get("warnings")
    removed_ids: list[str] = (
        [str(item) for item in cast(list[object], removed)]
        if isinstance(removed, list)
        else []
    )
    warning_strs: list[str] = (
        [str(item) for item in cast(list[object], warnings)]
        if isinstance(warnings, list)
        else []
    )
    return IntegrationDisconnectResponse(
        ok=True,
        disconnected=bool(data.get("disconnected")),
        removedConnectionIds=removed_ids,
        message=_optional_str(data.get("message")),
        warnings=warning_strs,
    )


def _assert_provider(provider: Provider) -> None:
    # `Provider` is a Literal["google"] today; the check is statically
    # unreachable but kept as a runtime guard for when other providers land.
    if provider != "google":
        raise HTTPException(  # pyright: ignore[reportUnreachable]
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration provider not found",
        )


def _ok_payload(response: JSONResponse) -> dict[str, object]:
    raw_data = cast(object, json.loads(bytes(response.body).decode("utf-8")))
    if not isinstance(raw_data, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid provider response",
        )
    data = cast(dict[str, object], raw_data)
    if response.status_code >= 400 or data.get("ok") is False:
        status_code = (
            response.status_code
            if response.status_code >= 400
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail=data.get("detail")
            or data.get("error")
            or "Integration request failed",
        )
    return data


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
