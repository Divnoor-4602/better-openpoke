from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import TypeAlias, cast

from fastapi import status
from fastapi.responses import JSONResponse

from ...config import Settings, get_settings
from ...core.workspace_context import get_current_workspace
from ...logging_config import logger
from ...models import GoogleConnectPayload, GoogleDisconnectPayload, GoogleStatusPayload
from ...utils import error_response
from .connections import list_workspaces_with_gmail

JsonDict: TypeAlias = dict[str, object]

_CLIENT_LOCK = threading.Lock()
_client: object | None = None

_PROFILE_CACHE: dict[str, JsonDict] = {}
_PROFILE_CACHE_LOCK = threading.Lock()


def _normalized(value: object) -> str:
    return str(value or "").strip()


def resolve_workspace_gmail_user_id() -> str | None:
    """Return the Composio user_id for the current workspace, or None.

    The Composio `user_id` is the workspace handle by API design — the
    integrations route forces `payload.user_id = workspace_id` on every
    connect/status/disconnect call. So "what user_id do I send to
    Composio?" reduces to "what workspace is bound to this context, and
    is it actually connected to Gmail?".

    Returns None when either (a) no workspace is bound (callers in this
    state should surface a "Gmail not connected" message rather than
    crash) or (b) the workspace has no entry in the gmail registry yet.
    """
    workspace_id = get_current_workspace()
    if not workspace_id:
        return None
    if workspace_id not in set(list_workspaces_with_gmail()):
        return None
    return workspace_id


def _default_google_user_id() -> str:
    return (
        os.getenv("OPENPOKE_GOOGLE_USER_ID")
        or os.getenv("COMPOSIO_GOOGLE_USER_ID")
        or "openpoke-web"
    )


def _gmail_import_client() -> Callable[..., object]:
    from composio import Composio  # type: ignore[import-untyped]

    return cast(Callable[..., object], Composio)


def _get_composio_client(settings: Settings | None = None) -> object:
    global _client
    if _client is not None:
        return _client

    with _CLIENT_LOCK:
        if _client is None:
            resolved_settings = settings or get_settings()
            composio = _gmail_import_client()
            api_key = resolved_settings.composio_api_key
            try:
                _client = composio(api_key=api_key) if api_key else composio()
            except TypeError as exc:
                if api_key:
                    raise RuntimeError(
                        "Installed Composio SDK does not accept the api_key argument; upgrade the SDK or remove COMPOSIO_API_KEY."
                    ) from exc
                _client = composio()
    return _client


def _extract_email(obj: object) -> str | None:
    if obj is None:
        return None

    direct_keys = (
        "email",
        "email_address",
        "emailAddress",
        "user_email",
        "provider_email",
        "account_email",
    )
    obj_map = _as_mapping(obj)
    for key in direct_keys:
        value = _attr(obj, key)
        if isinstance(value, str) and "@" in value:
            return value
        if obj_map is not None:
            value = obj_map.get(key)
            if isinstance(value, str) and "@" in value:
                return value

    if obj_map is not None:
        email_addresses = obj_map.get("emailAddresses")
        if isinstance(email_addresses, (list, tuple)):
            for entry in cast(list[object] | tuple[object, ...], email_addresses):
                entry_map = _as_mapping(entry)
                if entry_map is not None:
                    candidate = (
                        entry_map.get("value")
                        or entry_map.get("email")
                        or entry_map.get("emailAddress")
                    )
                    if isinstance(candidate, str) and "@" in candidate:
                        return candidate
                elif isinstance(entry, str) and "@" in entry:
                    return entry

        nested_paths = (
            ("profile", "email"),
            ("profile", "emailAddress"),
            ("user", "email"),
            ("data", "email"),
            ("data", "user", "email"),
            ("provider_profile", "email"),
        )
        for path in nested_paths:
            current: object | None = obj_map
            for segment in path:
                current_map = _as_mapping(current)
                if current_map is None or segment not in current_map:
                    current = None
                    break
                current = current_map[segment]
            if isinstance(current, str) and "@" in current:
                return current

    return None


def _cache_profile(user_id: str, profile: JsonDict) -> None:
    sanitized = _normalized(user_id)
    if not sanitized:
        return
    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE[sanitized] = {
            "profile": profile,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }


def _get_cached_profile(user_id: object) -> JsonDict | None:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    with _PROFILE_CACHE_LOCK:
        payload = _PROFILE_CACHE.get(sanitized)
        profile = _as_dict(payload.get("profile")) if payload else None
        return profile


def _clear_cached_profile(user_id: object = None) -> None:
    with _PROFILE_CACHE_LOCK:
        if user_id:
            _ = _PROFILE_CACHE.pop(_normalized(user_id), None)
        else:
            _PROFILE_CACHE.clear()


def _fetch_profile_from_composio(user_id: object) -> JsonDict | None:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    try:
        result = execute_google_tool(
            "GOOGLESUPER_GET_PROFILE", sanitized, arguments={"user_id": "me"}
        )
    except RuntimeError as exc:
        logger.warning("GOOGLESUPER_GET_PROFILE invocation failed: %s", exc)
        return None
    except Exception:  # pragma: no cover - defensive
        logger.exception(
            "Unexpected error fetching Gmail profile", extra={"user_id": sanitized}
        )
        return None

    profile: JsonDict | None = None
    if data := _as_dict(result.get("data")):
        profile = data
    elif data := _as_dict(result.get("profile")):
        profile = data
    elif data := _as_dict(result.get("response_data")):
        profile = data
    elif isinstance(result.get("items"), list):
        for item in cast(list[object], result["items"]):
            item_map = _as_mapping(item)
            if item_map is None:
                continue
            data_dict = _as_dict(item_map.get("data"))
            if data_dict is not None:
                profile = (
                    _as_dict(data_dict.get("response_data"))
                    or _as_dict(data_dict.get("profile"))
                    or data_dict
                )
            else:
                profile = _as_dict(item_map.get("response_data")) or _as_dict(
                    item_map.get("profile")
                )
            if profile is not None:
                break
    elif result.get("successful") is True:
        profile = _as_dict(result.get("result"))
    elif all(
        not isinstance(result.get(key), dict) for key in ("data", "profile", "result")
    ):
        profile = result if result else None

    if profile is not None:
        _cache_profile(sanitized, profile)
        return profile

    logger.warning(
        "Received unexpected Gmail profile payload",
        extra={"user_id": sanitized, "raw": result},
    )
    return None


def initiate_connect(payload: GoogleConnectPayload, settings: Settings) -> JSONResponse:
    auth_config_id = payload.auth_config_id or ""
    if not auth_config_id:
        return _error_response(
            "Missing auth_config_id. Set COMPOSIO_GOOGLE_AUTH_CONFIG_ID or pass auth_config_id.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user_id = payload.user_id or _default_google_user_id()
    _clear_cached_profile(user_id)
    try:
        client = _get_composio_client(settings)
        connected_accounts = _attr(client, "connected_accounts")
        list_connections = _attr(connected_accounts, "list")
        if callable(list_connections):
            existing = list_connections(
                auth_config_ids=[auth_config_id],
                statuses=["ACTIVE"],
                user_ids=[user_id],
            )
            existing_items = _list_response_items(existing)
            if existing_items:
                return JSONResponse(
                    {
                        "ok": True,
                        "redirect_url": None,
                        "connection_request_id": None,
                        "user_id": user_id,
                    }
                )

        link = _attr(connected_accounts, "link")
        if not callable(link):
            raise RuntimeError(
                "Installed Composio SDK does not expose connected_accounts.link; upgrade the SDK to connect Gmail."
            )
        link_kwargs = {
            "auth_config_id": auth_config_id,
            "user_id": user_id,
        }
        if payload.return_to:
            link_kwargs["callback_url"] = payload.return_to

        req = link(**link_kwargs)
        return JSONResponse(
            {
                "ok": True,
                "redirect_url": _attr(req, "redirect_url") or _attr(req, "redirectUrl"),
                "connection_request_id": _attr(req, "id"),
                "user_id": user_id,
            }
        )
    except Exception as exc:
        logger.exception("gmail connect failed", extra={"user_id": user_id})
        return _error_response(
            "Failed to initiate Gmail connect",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def fetch_status(payload: GoogleStatusPayload) -> JSONResponse:
    connection_request_id = _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id) or _default_google_user_id()

    if not connection_request_id and not user_id:
        return JSONResponse(
            {
                "ok": True,
                "connected": False,
                "status": "DISCONNECTED",
                "email": None,
                "user_id": None,
                "profile": None,
                "profile_source": "none",
            }
        )

    try:
        client = _get_composio_client()
        connected_accounts = _attr(client, "connected_accounts")
        account: object | None = None
        if connection_request_id:
            try:
                wait_for_connection = cast(
                    Callable[..., object],
                    _attr(connected_accounts, "wait_for_connection"),
                )
                account = wait_for_connection(connection_request_id, timeout=2.0)
            except Exception:
                try:
                    get_connection = cast(
                        Callable[..., object], _attr(connected_accounts, "get")
                    )
                    account = get_connection(connection_request_id)
                except Exception:
                    account = None
        if account is None and user_id:
            try:
                list_connections = cast(
                    Callable[..., object], _attr(connected_accounts, "list")
                )
                # Try filtered list first (Gmail or GOOGLESUPER, ACTIVE)
                items = list_connections(
                    user_ids=[user_id],
                    toolkit_slugs=["GMAIL", "GOOGLESUPER"],
                    statuses=["ACTIVE"],
                )
                data = _list_response_items(items)
                if data:
                    account = data[0]
                else:
                    # Fall back to unfiltered list — Composio may use a different
                    # toolkit slug for the connection or report a non-ACTIVE status.
                    items = list_connections(user_ids=[user_id])
                    data = _list_response_items(items)
                    if data:
                        # Prefer an account that looks active.
                        for candidate in data:
                            mapping = _as_mapping(candidate)
                            cand_status = str(
                                _attr(candidate, "status")
                                or (mapping.get("status") if mapping is not None else "")
                                or ""
                            ).upper()
                            if cand_status in {
                                "CONNECTED",
                                "ACTIVE",
                                "SUCCESS",
                                "SUCCESSFUL",
                                "COMPLETED",
                            }:
                                account = candidate
                                break
                        if account is None:
                            account = data[0]
                        logger.info(
                            "gmail status fallback list_connections matched",
                            extra={"user_id": user_id, "count": len(data)},
                        )
            except Exception:
                logger.exception(
                    "gmail status list_connections failed",
                    extra={"user_id": user_id},
                )
                account = None

        status_value: object = None
        email: str | None = None
        connected = False
        profile: JsonDict | None = None
        profile_source = "none"
        account_user_id: object = None

        if account is not None:
            account_map = _as_mapping(account)
            status_value = _attr(account, "status") or (
                account_map.get("status") if account_map is not None else None
            )
            normalized_status = str(status_value or "").upper()
            connected = normalized_status in {
                "CONNECTED",
                "SUCCESS",
                "SUCCESSFUL",
                "ACTIVE",
                "COMPLETED",
            }
            email = _extract_email(account)
            account_user_id = _attr(account, "user_id") or (
                account_map.get("user_id") if account_map is not None else None
            )

        if not user_id and account_user_id:
            user_id = _normalized(account_user_id)

        if connected and user_id:
            cached_profile = _get_cached_profile(user_id)
            if cached_profile:
                profile = cached_profile
                profile_source = "cache"
            else:
                fetched_profile = _fetch_profile_from_composio(user_id)
                if fetched_profile:
                    profile = fetched_profile
                    profile_source = "fetched"
            if profile and not email:
                email = _extract_email(profile)
        elif user_id:
            _clear_cached_profile(user_id)

        return JSONResponse(
            {
                "ok": True,
                "connected": bool(connected),
                "status": status_value or "UNKNOWN",
                "email": email,
                "user_id": user_id,
                "profile": profile,
                "profile_source": profile_source,
            }
        )
    except Exception as exc:
        logger.exception(
            "gmail status failed",
            extra={
                "connection_request_id": connection_request_id,
                "user_id": user_id,
            },
        )
        return _error_response(
            "Failed to fetch connection status",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def disconnect_account(payload: GoogleDisconnectPayload) -> JSONResponse:
    connection_id = _normalized(payload.connection_id) or _normalized(
        payload.connection_request_id
    )
    user_id = _normalized(payload.user_id) or _default_google_user_id()

    if not connection_id and not user_id:
        return _error_response(
            "Missing connection_id or user_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        client = _get_composio_client()
        connected_accounts = _attr(client, "connected_accounts")
    except Exception as exc:
        logger.exception(
            "gmail disconnect failed: client init", extra={"user_id": user_id}
        )
        return _error_response(
            "Failed to disconnect Gmail",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    removed_ids: list[str] = []
    errors: list[str] = []
    affected_user_ids: set[str] = set()

    def _delete_connection(identifier: str) -> None:
        sanitized_id = _normalized(identifier)
        if not sanitized_id:
            return
        try:
            get_connection = cast(
                Callable[..., object], _attr(connected_accounts, "get")
            )
            connection = get_connection(sanitized_id)
        except Exception:
            connection = None
        try:
            delete_connection = cast(
                Callable[..., object], _attr(connected_accounts, "delete")
            )
            _ = delete_connection(sanitized_id)
            removed_ids.append(sanitized_id)
            if connection is not None:
                connection_map = _as_mapping(connection)
                affected_user_ids.add(
                    _normalized(
                        _attr(connection, "user_id")
                        or (
                            connection_map.get("user_id")
                            if connection_map is not None
                            else None
                        )
                    )
                )
        except Exception as exc:  # pragma: no cover - depends on remote state
            logger.exception(
                "Failed to remove Gmail connection",
                extra={"connection_id": sanitized_id},
            )
            errors.append(str(exc))

    if connection_id:
        _delete_connection(connection_id)
    else:
        try:
            list_connections = cast(
                Callable[..., object], _attr(connected_accounts, "list")
            )
            items = list_connections(
                user_ids=[user_id], toolkit_slugs=["GMAIL", "GOOGLESUPER"]
            )
            data = _list_response_items(items)
        except Exception as exc:  # pragma: no cover - dependent on SDK
            logger.exception(
                "Failed to list Gmail connections", extra={"user_id": user_id}
            )
            return _error_response(
                "Failed to disconnect Gmail",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )

        if data:
            for entry in data:
                entry_map = _as_mapping(entry)
                candidate = _attr(entry, "id") or (
                    entry_map.get("id") if entry_map is not None else None
                )
                candidate_user_id = _attr(entry, "user_id") or (
                    entry_map.get("user_id") if entry_map is not None else None
                )
                if candidate:
                    if candidate_user_id:
                        affected_user_ids.add(_normalized(candidate_user_id))
                    _delete_connection(str(candidate))

    if user_id:
        affected_user_ids.add(user_id)

    for uid in list(affected_user_ids):
        if uid:
            _clear_cached_profile(uid)

    if errors and not removed_ids:
        return _error_response(
            "Failed to disconnect Gmail",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(errors),
        )

    response_payload: JsonDict = {
        "ok": True,
        "disconnected": bool(removed_ids),
        "removed_connection_ids": removed_ids,
    }
    if not removed_ids:
        response_payload["message"] = "No Gmail connection found"

    if errors:
        response_payload["warnings"] = errors
    return JSONResponse(response_payload)


def _normalize_tool_response(result: object) -> JsonDict:
    payload_dict: JsonDict | None = None
    try:
        model_dump = _attr(result, "model_dump")
        legacy_dict = _attr(result, "dict")
        if callable(model_dump):
            payload_dict = _as_dict(cast(Callable[[], object], model_dump)())
        elif callable(legacy_dict):
            payload_dict = _as_dict(cast(Callable[[], object], legacy_dict)())
    except Exception:
        payload_dict = None

    if payload_dict is None:
        try:
            model_dump_json = _attr(result, "model_dump_json")
            if callable(model_dump_json):
                loaded = cast(
                    object, json.loads(cast(Callable[[], str], model_dump_json)())
                )
                payload_dict = _as_dict(loaded)
        except Exception:
            payload_dict = None

    if payload_dict is None:
        if result_dict := _as_dict(result):
            payload_dict = result_dict
        elif isinstance(result, list):
            payload_dict = {"items": cast(list[object], result)}
        else:
            payload_dict = {"repr": str(result)}

    return payload_dict


def execute_google_tool(
    tool_name: str,
    composio_user_id: str,
    *,
    arguments: Mapping[str, object] | None = None,
) -> JsonDict:
    prepared_arguments: JsonDict = {}
    if isinstance(arguments, Mapping):
        for key, value in arguments.items():
            if value is not None:
                prepared_arguments[str(key)] = value

    _ = prepared_arguments.setdefault("user_id", "me")

    try:
        client = _get_composio_client()
        sdk_client = _attr(client, "client")
        tools = _attr(sdk_client, "tools")
        execute = cast(Callable[..., object], _attr(tools, "execute"))
        result = execute(
            tool_name,
            user_id=composio_user_id,
            arguments=prepared_arguments,
        )
        return _normalize_tool_response(result)
    except Exception as exc:
        logger.exception(
            "gmail tool execution failed",
            extra={"tool": tool_name, "user_id": composio_user_id},
        )
        raise RuntimeError(f"{tool_name} invocation failed: {exc}") from exc


def _attr(obj: object, name: str) -> object | None:
    return getattr(obj, name, None)


def _list_response_items(value: object) -> list[object]:
    items = _attr(value, "items") or _attr(value, "data")
    value_map = _as_mapping(value)
    if items is None and value_map is not None:
        items = value_map.get("items") or value_map.get("data")
    return cast(list[object], items) if isinstance(items, list) else []


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        str(key): item for key, item in cast(Mapping[object, object], value).items()
    }


def _as_dict(value: object) -> JsonDict | None:
    mapping = _as_mapping(value)
    return dict(mapping) if mapping is not None else None


def _error_response(
    message: str, *, status_code: int, detail: str | None = None
) -> JSONResponse:
    return error_response(message, status_code=status_code, detail=detail)
