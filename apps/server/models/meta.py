from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class RootResponse(BaseModel):
    status: str
    service: str
    version: str
    endpoints: list[str]


class SetTimezoneRequest(BaseModel):
    timezone: str


class SetTimezoneResponse(BaseModel):
    ok: bool = True
    timezone: str
