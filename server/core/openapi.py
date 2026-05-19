from __future__ import annotations

from typing import cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute


def install_custom_openapi(app: FastAPI) -> None:
    _assign_stable_operation_ids(app)

    def custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            description="OpenPoke public API",
        )
        _normalize_error_responses(schema)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _assign_stable_operation_ids(app: FastAPI) -> None:
    seen: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        base = route.name
        operation_id = base
        suffix = 2
        while operation_id in seen:
            operation_id = f"{base}_{suffix}"
            suffix += 1
        route.operation_id = operation_id
        seen.add(operation_id)


def _normalize_error_responses(schema: dict[str, object]) -> None:
    components = schema.setdefault("components", {})
    if not isinstance(components, dict):
        return
    components_map = cast(dict[str, object], components)
    schemas = components_map.setdefault("schemas", {})
    if not isinstance(schemas, dict):
        return
    schemas_map = cast(dict[str, object], schemas)
    if "ErrorResponse" not in schemas_map:
        return

    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return
    paths_map = cast(dict[str, object], paths)
    error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
    for path_item in paths_map.values():
        if not isinstance(path_item, dict):
            continue
        path_item_map = cast(dict[str, object], path_item)
        for operation in path_item_map.values():
            if not isinstance(operation, dict):
                continue
            operation_map = cast(dict[str, object], operation)
            responses = operation_map.setdefault("responses", {})
            if not isinstance(responses, dict):
                continue
            responses_map = cast(dict[str, object], responses)
            for status_code in ("400", "404", "422", "500"):
                responses_map[status_code] = {
                    "description": "Error response",
                    "content": {"application/json": {"schema": error_ref}},
                }
