"""Filesystem paths used by the server.

The data directory holds SQLite databases, JSON state files, and per-workspace
working memory. In production it should point at a persistent volume mount
(e.g. Railway's `/data`) via the `OPENPOKE_DATA_DIR` env var. Locally it
defaults to `server/data/` next to the source tree.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    override = os.getenv("OPENPOKE_DATA_DIR")
    path = Path(override).expanduser().resolve() if override else _DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path
