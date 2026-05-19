---
name: fastapi-patterns
description: Enforces FastAPI + Pydantic v2 patterns used in OpenPoke's `server/`. Triggers on any FastAPI route handler, dependency, pydantic model, middleware, OpenAPI customization, or JSONResponse handling. Covers `Annotated[X, Depends()]` deps, `ERROR_RESPONSES` typing, `JSONResponse.body` decoding, Pydantic v2 `ClassVar[ConfigDict]` / `model_validate`, middleware-return discard, and `RequestResponseEndpoint` typing.
metadata:
  scope: server/
  version: "1.0.0"
---

# FastAPI Patterns (OpenPoke server/)

Hard rules for `server/`. Each one was hit at least once while taking basedpyright from 813 warnings to 0 — they are not theoretical.

## 1. Dependencies use `Annotated`, never default-value `Depends()`

basedpyright's `reportCallInDefaultInitializer` flags every `param: T = Depends(get_x)`. The fix is the modern FastAPI idiom.

```python
# BAD
def route(workspace_id: str = Depends(get_workspace_id)) -> Resp: ...

# GOOD
from typing import Annotated
def route(workspace_id: Annotated[str, Depends(get_workspace_id)]) -> Resp: ...
```

When converting, **required Annotated params cannot follow defaulted params**. Reorder so required deps come first.

## 2. `ERROR_RESPONSES` must be typed at the source

```python
# server/core/errors.py
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {400: {...}, 404: {...}, ...}
```

Without the explicit type, pyright infers `dict[int, dict[str, Unknown]]`, which is invariant-incompatible with FastAPI's `dict[int | str, dict[str, Any]] | None` and errors at every `responses=ERROR_RESPONSES`. Fix at the source — never at the call sites.

## 3. `JSONResponse.body` is a `memoryview`

`json.loads(response.body)` fails type checks. Use `bytes(...)` first:

```python
data = cast(object, json.loads(bytes(response.body).decode("utf-8")))
```

The outer `cast(object, ...)` is required because `json.loads` returns `Any` — see basedpyright-strict skill, rule "Launder Any at the boundary."

## 4. Middleware registration has a return value

```python
# BAD — reportUnusedCallResult
app.middleware("http")(request_id_middleware)

# GOOD
_ = app.middleware("http")(request_id_middleware)
```

Same rule applies to `loop.create_task(...)`, `ContextVar.set(...)`, `set.discard(...)`, and any other call whose return value you intentionally ignore.

## 5. `call_next` is `RequestResponseEndpoint`

```python
# BAD
async def request_id_middleware(request: Request, call_next: Callable[[Request], object]):

# GOOD
from starlette.middleware.base import RequestResponseEndpoint
async def request_id_middleware(request: Request, call_next: RequestResponseEndpoint):
```

## 6. Pydantic v2 `model_config` needs `ClassVar[ConfigDict]`

basedpyright's `reportUnannotatedClassAttribute` fires unless the class is `@final` *or* the attr is annotated. Every BaseModel that sets `model_config` needs:

```python
from typing import ClassVar
from pydantic import BaseModel, ConfigDict

class Foo(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
```

## 7. Coerce loose dicts with `model_validate`, not `Model(**dict)`

When a dict comes from sqlite, json, or any external boundary (i.e. its values are `object`/`Any`), `Model(**row)` fails because keyword args become `object`. Use:

```python
items = [WorkspaceListEntry.model_validate(row) for row in rows]
```

This delegates type coercion to Pydantic instead of fighting the type checker.

## 8. `RequestValidationError.errors()` returns `Sequence`, not `list`

```python
from collections.abc import Sequence, Mapping
def _sanitize_validation_errors(errors: Sequence[Mapping[str, Any]]) -> ...:
```

## 9. `app.openapi` reassignment needs the type-ignore

`app.openapi = custom_openapi` is the documented FastAPI pattern but pyright sees it as a method assignment. The single permitted suppression here is:

```python
app.openapi = custom_openapi  # type: ignore[method-assign]
```

Do not generalize — only at this exact site.

## 10. Operation IDs and OpenAPI schema mutations

When walking the OpenAPI schema dict, cast at each `.setdefault(...)` boundary because the schema is `dict[str, object]` and child values lose typing:

```python
components_map = cast(dict[str, object], components)
schemas = components_map.setdefault("schemas", {})
```

See `server/core/openapi.py` for the canonical pattern.

## 11. No `dict[str, Any]` in request/response models

Replace with `dict[str, object]`. Pydantic still validates the field; the type checker stays clean. The only Pydantic boundary that may keep `Any` is `field_validator` input parameters where Pydantic itself uses `Any`.

## Boundary suppressions — where they're OK

These suppressions are accepted in this codebase **only** at external-library boundaries:

- `# pyright: ignore[reportUnknownMemberType]` — calling untyped third-party SDK methods (jsonschema, Composio, Pinecone)
- `# pyright: ignore[reportAny, reportExplicitAny]` — helper that accepts an `Any` parameter purely to launder it into a typed return

Everywhere else, write a Protocol or use the double-cast pattern from basedpyright-strict.

## Tests for routes

- Use `TestClient` via the `client` fixture in `server/tests/conftest.py` — it preloads Basic auth.
- For dep overrides, use `app.dependency_overrides[get_workspace_id] = stub`; clean up with `_ = app.dependency_overrides.pop(get_workspace_id, None)`.

## Self-check before declaring done

Run `/Users/divnoor/anaconda3/envs/better-openpoke/bin/basedpyright server` and `/Users/divnoor/anaconda3/envs/better-openpoke/bin/pytest server -q`. Both must report zero errors/warnings/failures.
