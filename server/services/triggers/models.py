from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class TriggerRecord(BaseModel):
    """Serialized trigger representation returned to callers."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    workspace_id: str
    agent_name: str
    payload: str
    start_time: str | None = None
    next_trigger: str | None = None
    recurrence_rule: str | None = None
    timezone: str | None = None
    status: str
    last_error: str | None = None
    created_at: str
    updated_at: str


__all__ = ["TriggerRecord"]
