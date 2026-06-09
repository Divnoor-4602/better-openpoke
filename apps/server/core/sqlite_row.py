"""Honest type for ``sqlite3.Row``-style result rows.

``sqlite3.Row`` is duck-typed: it supports ``row[key]``, ``row.keys()``,
``len(row)``, and iteration — but **not** ``.values()``, ``.items()``,
or ``.get()``. Casting a row to ``Mapping[str, object]`` advertises
those missing methods to the type checker and produces runtime
``AttributeError`` whenever a caller takes the bait.

Use ``SqliteRow`` for any helper that returns or accepts a row read
from a connection whose ``row_factory`` is set to ``sqlite3.Row``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol


class SqliteRow(Protocol):
    """The actual surface ``sqlite3.Row`` exposes."""

    def __getitem__(self, key: int | str, /) -> object: ...
    def __iter__(self) -> Iterator[object]: ...
    def __len__(self) -> int: ...
    def keys(self) -> list[str]: ...


__all__ = ["SqliteRow"]
