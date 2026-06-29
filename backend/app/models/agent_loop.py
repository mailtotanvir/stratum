from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AgentLoopStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class AgentLoopToolDefinition(BaseModel):
    name: str
    description: str
    argument_schema: dict[str, Any]
    completion_tool: bool = False


class AgentLoopToolCall(BaseModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool")
    @classmethod
    def require_non_empty_tool(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentLoopToolResult(BaseModel):
    tool: str = Field(min_length=1)
    output: str
    completion_intent: bool = False


class AgentLoopStep(BaseModel):
    iteration: int = Field(ge=1)
    provider_output: str | None = None
    tool_call: AgentLoopToolCall | None = None
    tool_result: AgentLoopToolResult | None = None
    error: str | None = None


class AgentLoopRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_request: str = Field(min_length=1)
    max_iterations: int = Field(default=5, ge=1)
    provider_id: str | None = None
    model: str | None = None

    @field_validator("session_id", "user_request")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("provider_id", "model")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentLoopSmokeRequest(BaseModel):
    session_id: str | None = Field(default=None, min_length=1)
    user_request: str = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1)
    provider_id: str | None = None
    model: str | None = None

    @field_validator("session_id", "provider_id", "model")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("user_request")
    @classmethod
    def require_non_empty_user_request(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentLoopStopRequest(BaseModel):
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentLoopStopResponse(BaseModel):
    session_id: str
    stop_requested: bool


class AgentLoopRunSummary(BaseModel):
    session_id: str
    status: AgentLoopStatus
    user_request: str | None = None
    provider_id: str | None = None
    model: str | None = None
    iterations_used: int = Field(default=0, ge=0)
    final_answer: str | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    stopped_at: str | None = None


class AgentLoopResult(BaseModel):
    session_id: str
    status: AgentLoopStatus
    final_answer: str | None = None
    iterations_used: int = Field(ge=0)
    steps: list[AgentLoopStep] = Field(default_factory=list)
    error: str | None = None
