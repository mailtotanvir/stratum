from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.provider_execution import (
    ProviderExecutionResult,
    ProviderMessage,
    ProviderStreamMode,
)


class AgentExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentExecutionMode(StrEnum):
    SINGLE_TURN = "single_turn"
    TOOL_ENABLED = "tool_enabled"


class AgentExecutionRequest(BaseModel):
    runtime_session_id: str = Field(min_length=1)
    task_id: str | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mode: AgentExecutionMode
    messages: list[ProviderMessage]
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    stream_mode: ProviderStreamMode = ProviderStreamMode.NONE
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runtime_session_id", "provider", "model")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentExecutionResult(BaseModel):
    status: AgentExecutionStatus
    provider_execution_record_id: str | None = None
    provider_result: ProviderExecutionResult | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionRecord(BaseModel):
    id: str = Field(min_length=1)
    request: AgentExecutionRequest
    result: AgentExecutionResult | None = None
    status: AgentExecutionStatus
    created_at: datetime
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def require_non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value
