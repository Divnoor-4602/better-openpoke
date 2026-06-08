---
name: openpoke-basedpyright-strict
description: OpenPoke portable copy of the basedpyright-strict skill. Enforces basedpyright strict-mode conformance rules used in OpenPoke's `server/`. Triggers on any Python code in `server/` that uses `Any`, `cast`, sqlite/json/external-library boundaries, class attributes without annotations, ignored return values, untyped TestCase overrides, or lazy `__getattr__` modules. Covers `Any`→`object` replacement, the `cast(T, cast(object, x))` double-cast pattern, `_ =` for `reportUnusedCallResult`, `@override` for TestCase, Protocol-based typing for untyped third-party libs, and where boundary `# pyright: ignore` is acceptable.
metadata:
  scope: server/
  version: "1.0.0"
---

# basedpyright-strict (OpenPoke server/)

`server/` runs basedpyright with the default ruleset (which is stricter than vanilla pyright — `reportAny`, `reportExplicitAny`, `reportUnannotatedClassAttribute`, `reportUnusedCallResult`, `reportPrivateUsage`, `reportImplicitOverride`, `reportImplicitStringConcatenation`, `reportCallInDefaultInitializer`, etc. are all on). The bar is **0 errors, 0 warnings**. No relaxing rules, no `cast(Any, …)` band-aids.

Run: `/Users/divnoor/anaconda3/envs/better-openpoke/bin/basedpyright server`.

## 1. Default to `object`, not `Any`

`reportExplicitAny` fires on every `Any`. `object` is the right base type for "anything" in a typed codebase — narrow via `isinstance` when you need to use it.

```python
# BAD
def get_payload() -> dict[str, Any]: ...

# GOOD
def get_payload() -> dict[str, object]: ...
```

`Any` is permitted only at three boundaries (see rule 8).

## 2. Launder `Any` at the boundary with the double-cast pattern

`json.loads`, `sqlite3.Row.__getitem__`, untyped SDK returns, and Pydantic `field_validator` inputs all return `Any`. Convert to a typed value with:

```python
data = cast(object, json.loads(raw))           # for unknown-shape values
mapping = cast(Mapping[str, object], cast(object, row))  # for sqlite rows
```

The inner `cast(object, ...)` strips the `Any`; the outer one re-types it. Single-cast `cast(Mapping[str, object], row)` fires `reportInvalidCast` because pyright sees you converting Any → concrete.

Build module-level helpers when you do this often (see `server/db/threads.py`, `server/services/memory/store.py`):

```python
def _row(value: Any) -> Mapping[str, object] | None:  # pyright: ignore[reportExplicitAny, reportAny]
    if value is None:
        return None
    return cast(Mapping[str, object], cast(object, value))

def _rows(values: Any) -> list[Mapping[str, object]]:  # pyright: ignore[reportExplicitAny, reportAny]
    return cast("list[Mapping[str, object]]", cast(object, values))
```

## 3. Prefix ignored return values with `_ =`

`reportUnusedCallResult` fires on any call whose return value is discarded. Use `_` (the conventional "throwaway"), not a comment.

```python
# BAD
self._entries.pop(request_id, None)
loop.create_task(_run())
_current_workspace.set(workspace_id)   # returns Token
os.environ.setdefault("KEY", "value")  # returns str

# GOOD
_ = self._entries.pop(request_id, None)
_ = loop.create_task(_run())
_ = _current_workspace.set(workspace_id)
_ = os.environ.setdefault("KEY", "value")
```

Calls that *should* return something but are written for side effects (like `_store.update(...)` returning `bool`) get the same treatment.

## 4. Annotate every class attribute when class is not `@final`

`reportUnannotatedClassAttribute` requires either `@final` on the class or an explicit annotation on every attribute assigned in `__init__` (or class body).

```python
class TaskRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock: threading.Lock = threading.Lock()  # annotation required

class _WorkspaceState:
    __slots__: tuple[str, ...] = ("seen_store", "has_seeded_initial_snapshot")  # __slots__ counts
```

Pydantic `model_config` follows the same rule: `model_config: ClassVar[ConfigDict] = ConfigDict(...)`.

## 5. `@override` on unittest TestCase methods

```python
from typing import override

class MyTests(unittest.TestCase):
    @override
    def setUp(self) -> None: ...
    @override
    def tearDown(self) -> None: ...
```

`reportImplicitOverride` flags any method that overrides without the decorator.

## 6. Lazy `__getattr__` modules return `object`, not `Any`

```python
# BAD — reportAny + reportExplicitAny
def __getattr__(name: str) -> Any: ...

# GOOD
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .submod import Thing as Thing  # for IDE/static visibility

def __getattr__(name: str) -> object: ...
```

If the inner `return getattr(module, attr_name)` still complains, scope the suppression: `return getattr(module, attr_name)  # pyright: ignore[reportAny]`.

## 7. Protocols for untyped third-party libs and to break import cycles

When you import an external client whose stubs are missing/wrong (Pinecone, etc.) or when a TYPE_CHECKING re-import creates a cycle, write a local `Protocol` that captures only the surface area you call. See `server/services/memory/indexer.py` (Pinecone) and `server/agents/execution_agent/batch_manager.py` (`_InteractionRuntime`).

```python
class _PineconeIndex(Protocol):
    def upsert(self, *, vectors: list[dict[str, object]], namespace: str) -> None: ...
```

For asyncio interop, the return type must be `Coroutine[Any, Any, T]`, not `Awaitable[T]` — `asyncio.create_task`/`asyncio.run` require Coroutine.

## 8. Where `Any` and `# pyright: ignore` are acceptable

Three boundaries only:

1. **Helper functions whose entire purpose is to launder `Any`** — accept `Any` as parameter, return a typed value. Suppress at the signature: `def _row(value: Any) -> Mapping[str, object] | None:  # pyright: ignore[reportExplicitAny, reportAny]`.
2. **Untyped third-party method calls** that no Protocol can model (e.g. `Draft202012Validator(schema).iter_errors(args)  # pyright: ignore[reportUnknownMemberType, reportAny]`).
3. **Test files exercising protected methods** — use a file-scope pragma at the top instead of per-line ignores: `# pyright: reportPrivateUsage=false`.

Forbidden everywhere else:

- `cast(Any, value)` — use `object` instead.
- `# type: ignore` without a specific rule (use `# pyright: ignore[rule]`).
- Module-wide `# pyright: ignore[reportAny, reportExplicitAny]` at the top of source files (only test files get the file-scope pragma).
- Relaxing severity in a config file.

## 9. Implicit string concatenation

`reportImplicitStringConcatenation` flags `"foo " "bar"`. Either join with `+` or write the string on one line. The codebase prefers single-line strings even if long.

## 10. Unused imports

`reportUnusedImport` flags any imported name that isn't referenced. Remove it, even if it was kept "for re-export" — re-exports must go through `__all__` plus `if TYPE_CHECKING:` aliases (`from .mod import X as X`).

## 11. `reportUnnecessaryCast` / `reportUnnecessaryTypeIgnoreComment`

If basedpyright tells you a cast or ignore is unnecessary, **delete it**. Don't suppress the suppression-check warning.

## Self-check

```
/Users/divnoor/anaconda3/envs/better-openpoke/bin/basedpyright server
/Users/divnoor/anaconda3/envs/better-openpoke/bin/pytest server -q
```

Both must report zero issues before declaring done.
