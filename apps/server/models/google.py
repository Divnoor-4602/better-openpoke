from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class GoogleConnectPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(default=None, alias="user_id")
    auth_config_id: str | None = Field(default=None, alias="auth_config_id")
    return_to: str | None = Field(default=None, alias="return_to")


class GoogleStatusPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(default=None, alias="user_id")
    connection_request_id: str | None = Field(
        default=None, alias="connection_request_id"
    )


class GoogleDisconnectPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(default=None, alias="user_id")
    connection_id: str | None = Field(default=None, alias="connection_id")
    connection_request_id: str | None = Field(
        default=None, alias="connection_request_id"
    )
