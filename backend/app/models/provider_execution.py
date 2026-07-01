from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ProviderExecutionStatus(StrEnum):
    REQUESTED = "requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProviderMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProviderExecutionMode(StrEnum):
    CHAT = "chat"
    COMPLETION = "completion"
    TOOL_CALL = "tool_call"


class ProviderStreamMode(StrEnum):
    NONE = "none"
    SSE = "sse"
    CHUNKED = "chunked"


class ProviderMessage(BaseModel):
    role: ProviderMessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderExecutionRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mode: ProviderExecutionMode
    messages: list[ProviderMessage] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    stream_mode: ProviderStreamMode = ProviderStreamMode.NONE
    runtime_session_id: str | None = None
    task_id: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def provider_id(self) -> str:
        return self.provider

    @field_validator("provider", "model")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_messages_for_mode(self) -> "ProviderExecutionRequest":
        if self.mode in {
            ProviderExecutionMode.CHAT,
            ProviderExecutionMode.TOOL_CALL,
        } and not self.messages:
            raise ValueError(
                "messages must not be empty for chat or tool_call mode"
            )
        return self


class ProviderUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def derive_total_tokens(self) -> "ProviderUsage":
        if (
            self.total_tokens is None
            and self.input_tokens is not None
            and self.output_tokens is not None
        ):
            self.total_tokens = self.input_tokens + self.output_tokens
        return self


class ProviderExecutionResult(BaseModel):
    status: ProviderExecutionStatus
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    effective_provider_id: str | None = None
    effective_model: str | None = None
    routing_reason: str | None = None
    routing_source: str | None = None
    budget_mode: str | None = None
    task_type: str | None = None
    content: str | None = None
    raw_response: dict[str, Any] | None = None
    usage: ProviderUsage | None = None
    error_message: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "model")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_result_status(self) -> "ProviderExecutionResult":
        if self.status == ProviderExecutionStatus.FAILED and (
            self.error_message is None or not self.error_message.strip()
        ):
            raise ValueError("failed provider results require error_message")
        return self


class ProviderExecutionStreamEvent(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    content: str | None = None
    done: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderExecutionRecord(BaseModel):
    id: str = Field(min_length=1)
    request: ProviderExecutionRequest
    result: ProviderExecutionResult | None = None
    status: ProviderExecutionStatus
    created_at: datetime
    completed_at: datetime | None = None
    runtime_session_id: str | None = None
    task_id: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def require_non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @property
    def provider_id(self) -> str:
        return self.request.provider_id
