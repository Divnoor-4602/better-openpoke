from __future__ import annotations

import base64
import binascii

from pydantic import BaseModel, Field

MAX_CURSOR_OFFSET = 10000


class CursorPage(BaseModel):
    nextCursor: str | None = Field(default=None)
    limit: int = Field(ge=1, le=100)


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        decoded = int(raw)
        return max(0, min(decoded, MAX_CURSOR_OFFSET))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return 0


def encode_cursor(offset: int | None) -> str | None:
    if offset is None:
        return None
    return base64.urlsafe_b64encode(str(max(0, offset)).encode("ascii")).decode("ascii")
