from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Request, Response

REQUEST_ID_HEADER = "x-request-id"


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return str(uuid.uuid4())


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], object],
) -> Response:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    stripped = incoming.strip() if incoming else ""
    request_id = stripped or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
