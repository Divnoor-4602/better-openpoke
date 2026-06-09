"""Loader for tool-call JSON Schemas generated from the web catalog.

The source of truth lives in
``apps/web/src/features/assistant/components/catalog/schemas.ts`` as Zod
schemas. A predev/prebuild script (``bun run generate:tool-schemas``)
converts those to JSON Schema and writes ``apps/server/generated/tool_schemas.json``
which this module reads at import time.

The same JSON is used in two places:

* Tool definitions (``apps/server/agents/.../tools*.py``) embed it as the
  ``parameters`` block sent to the LLM so the model sees the catalog's
  exact contract.
* The agent runtimes call :func:`validate_tool_args` before dispatch so a
  malformed call never reaches the Python tool function — the LLM is asked
  to retry with a structured error message instead.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, cast

from jsonschema import Draft202012Validator

# Per-tool budget for validation-failure retries inside one agent run. Set
# tight (3 total attempts) so a model stuck re-emitting the same bad call
# burns through quickly instead of monopolizing the whole MAX_TOOL_ITERATIONS.
MAX_VALIDATION_RETRIES_PER_TOOL: int = 2

_SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "generated"
    / "tool_schemas.json"
)

TOOL_SCHEMAS: dict[str, dict[str, object]] = cast(
    dict[str, dict[str, object]], cast(object, json.loads(_SCHEMA_PATH.read_text()))
)


def validate_tool_args(tool_name: str, args: dict[str, object]) -> list[str]:
    """Return a list of human-readable validation errors, or an empty list
    if ``args`` satisfies the schema for ``tool_name``. Tools without a
    registered schema (i.e. not surfaced through the web catalog) are
    skipped — they keep their hand-written, server-only contracts.
    """
    schema = TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        return []
    return _collect_errors(schema, args)


def _collect_errors(
    schema: dict[str, object],
    args: Any,  # pyright: ignore[reportExplicitAny, reportAny]
) -> list[str]:
    # `jsonschema` types `iter_errors` parameter as `_JsonParameter` (an
    # internal ADT). Take an Any here so the public API stays typed without
    # leaking that internal type.
    return [
        str(cast(object, error.message))
        for error in Draft202012Validator(schema).iter_errors(args)  # pyright: ignore[reportUnknownMemberType, reportAny]
    ]
