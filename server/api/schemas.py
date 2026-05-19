from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.pagination import CursorPage


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class MeResponse(BaseModel):
    workspaceId: str


class TimezoneSetRequest(BaseModel):
    timezone: str = Field(min_length=1)


class TimezoneResponse(BaseModel):
    ok: bool = True
    timezone: str


class DeleteResponse(BaseModel):
    ok: bool = True


class ThreadResource(BaseModel):
    threadId: str
    title: str | None = None
    createdAt: str
    updatedAt: str


class ThreadCreateResponse(BaseModel):
    thread: ThreadResource


class ThreadListResponse(BaseModel):
    items: list[ThreadResource]
    page: CursorPage


class ThreadResponse(BaseModel):
    thread: ThreadResource


class ThreadUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TextUIPart(BaseModel):
    type: Literal["text"]
    text: str


class GenericUIPart(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    type: str = Field(min_length=1)


MessageRole = Literal["system", "user", "assistant", "tool", "data"]


class UIMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    id: str | None = None
    role: MessageRole
    content: str | None = None
    parts: list[TextUIPart | GenericUIPart] = Field(default_factory=list)

    def text_content(self) -> str:
        if self.content is not None:
            return self.content
        text_parts: list[str] = []
        for part in self.parts:
            if isinstance(part, TextUIPart):
                text_parts.append(part.text)
        return "".join(text_parts)

    def serializable_parts(self) -> list[dict[str, object]]:
        return [part.model_dump(mode="json") for part in self.parts]


class MessageResource(BaseModel):
    messageId: str
    threadId: str
    role: MessageRole
    content: str
    parts: list[TextUIPart | GenericUIPart] = Field(default_factory=list)
    createdAt: str
    turnIndex: int = 0


class MessageCreateRequest(BaseModel):
    message: UIMessage


class MessageCreateResponse(BaseModel):
    message: MessageResource


class MessageListResponse(BaseModel):
    items: list[MessageResource]
    page: CursorPage


NotificationPermission = Literal["granted", "default", "denied"]


class MessageStreamRequest(BaseModel):
    messages: list[UIMessage] = Field(min_length=1)
    timezone: str | None = Field(default=None, min_length=1)
    notifications: NotificationPermission | None = Field(default=None)


class StreamPartSchema(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    type: str


class AgentRunEventResource(BaseModel):
    id: int | None
    runId: str
    sequence: int
    type: str
    state: str | None = None
    toolCallId: str | None = None
    toolName: str | None = None
    text: str | None = None
    input: object | None = None
    output: object | None = None
    error: str | None = None
    createdAt: str


class AgentRunResource(BaseModel):
    runId: str
    requestId: str
    memoryId: str
    threadId: str | None = None
    parentMemoryId: str | None = None
    parentRunId: str | None = None
    scope: Literal["interaction", "execution"] = "execution"
    title: str
    status: Literal["queued", "running", "completed", "failed"]
    ok: bool | None = None
    createdAt: str
    updatedAt: str
    parts: list[AgentRunEventResource] = Field(default_factory=list)


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResource]
    page: CursorPage


class AgentRunResponse(BaseModel):
    run: AgentRunResource


class AgentRunCreateRequest(BaseModel):
    memoryId: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    instructions: str = Field(min_length=1)
    requestId: str | None = Field(default=None, min_length=1, max_length=200)
    parentMemoryId: str | None = Field(default=None, max_length=200)


Provider = Literal["google"]


class IntegrationConnectRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    userId: str | None = Field(default=None, alias="userId")
    authConfigId: str | None = Field(default=None, alias="authConfigId")
    returnTo: str | None = Field(default=None, alias="returnTo")


class IntegrationConnectResponse(BaseModel):
    ok: bool
    redirectUrl: str | None = None
    connectionRequestId: str | None = None
    userId: str | None = None


class IntegrationStatusRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    userId: str | None = Field(default=None, alias="userId")
    connectionRequestId: str | None = Field(default=None, alias="connectionRequestId")


class IntegrationStatusResponse(BaseModel):
    ok: bool
    connected: bool
    status: str
    email: str | None = None
    userId: str | None = None
    profile: dict[str, object] | None = None
    profileSource: str


class IntegrationDisconnectRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    userId: str | None = Field(default=None, alias="userId")
    connectionId: str | None = Field(default=None, alias="connectionId")
    connectionRequestId: str | None = Field(default=None, alias="connectionRequestId")


class IntegrationDisconnectResponse(BaseModel):
    ok: bool
    disconnected: bool
    removedConnectionIds: list[str] = Field(default_factory=list)
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("warnings", mode="before")
    @classmethod
    def _default_warnings(cls, value: object) -> object:
        return [] if value is None else value


class DraftUpdateRequest(BaseModel):
    """Flat partial — all fields optional. Server omits ``None`` when building
    the Composio ``message`` payload so unset fields are never cleared."""

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    subject: str | None = None
    body: str | None = None
    to: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None


class DraftSendResponse(BaseModel):
    ok: bool = True
    status: Literal["sent"] = "sent"
    threadId: str | None = None
    messageId: str | None = None


class DraftUpdateResponse(BaseModel):
    ok: bool = True
    draftId: str


class DraftDiscardResponse(BaseModel):
    ok: bool = True
    status: Literal["discarded"] = "discarded"


class CalendarEventUpdateRequest(BaseModel):
    """Flat partial — all fields optional. Server omits ``None`` when
    building the Composio payload so unset fields are never cleared."""

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    summary: str | None = None
    description: str | None = None
    attendees: list[str] | None = None


class CalendarEventUpdateResponse(BaseModel):
    ok: bool = True
    eventId: str


class CalendarEventDiscardResponse(BaseModel):
    ok: bool = True
    status: Literal["discarded"] = "discarded"
