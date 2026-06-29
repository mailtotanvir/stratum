from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.provider_execution import ProviderMessageRole


class OpenAIChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ProviderMessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class OpenAIChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    messages: list[OpenAIChatMessage] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    stream: bool


class OpenAIChatResponseMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["assistant"]
    content: str = Field(min_length=1)


class OpenAIChatResponseChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int | None = Field(default=None, ge=0)
    message: OpenAIChatResponseMessage
    finish_reason: str | None = None


class OpenAIChatResponseUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class OpenAIChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    model: str | None = None
    choices: list[OpenAIChatResponseChoice] = Field(min_length=1)
    usage: OpenAIChatResponseUsage | None = None


class OpenAIChatStreamDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["assistant"] | None = None
    content: str | None = None


class OpenAIChatStreamChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int | None = Field(default=None, ge=0)
    delta: OpenAIChatStreamDelta
    finish_reason: str | None = None


class OpenAIChatStreamChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    model: str | None = None
    choices: list[OpenAIChatStreamChoice] = Field(min_length=1)
