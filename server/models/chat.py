from __future__ import annotations

from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    role: str = Field(..., min_length=1)
    content: str = Field(...)
    timestamp: str | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _coerce_content(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        raw_data = cast(dict[object, object], data)
        if "content" not in raw_data:
            return raw_data

        coerced = {str(key): value for key, value in raw_data.items()}
        content = coerced["content"]
        coerced["content"] = "" if content is None else str(content)
        return coerced

    def as_openrouter(self) -> dict[str, str]:
        return {"role": self.role.strip(), "content": self.content}


class ChatRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        populate_by_name=True, extra="ignore"
    )

    messages: list[ChatMessage] = Field(default_factory=list)
    model: str | None = None
    system: str | None = None
    stream: bool = True

    def openrouter_messages(self) -> list[dict[str, str]]:
        return [msg.as_openrouter() for msg in self.messages if msg.content.strip()]


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatHistoryClearResponse(BaseModel):
    ok: bool = True
