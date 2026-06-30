from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AgentLoopStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    PAUSED = "paused"


class AgentLoopApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentLoopToolDefinition(BaseModel):
    name: str
    description: str
    argument_schema: dict[str, Any]
    completion_tool: bool = False
    requires_approval: bool = False


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
    event_metadata: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
    )


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
    workspace_id: str | None = None
    provider_id: str | None = None
    model: str | None = None

    @field_validator("session_id", "user_request")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("workspace_id", "provider_id", "model")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentLoopSmokeRequest(BaseModel):
    session_id: str | None = Field(default=None, min_length=1)
    user_request: str = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1)
    workspace_id: str | None = None
    provider_id: str | None = None
    model: str | None = None

    @field_validator("session_id", "workspace_id", "provider_id", "model")
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


class AgentLoopApprovalRequest(BaseModel):
    approval_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    tool: str = Field(min_length=1)
    arguments: dict[str, Any]
    status: AgentLoopApprovalStatus
    reason: str | None = None


class AgentLoopApprovalResponseRequest(BaseModel):
    approved: bool
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentLoopApprovalResumeResult(BaseModel):
    approval_id: str
    session_id: str
    status: AgentLoopApprovalStatus
    tool: str
    executed: bool
    already_resumed: bool = False
    tool_result: AgentLoopToolResult | None = None
    reason: str | None = None


class AgentLoopRunSummary(BaseModel):
    session_id: str
    status: AgentLoopStatus
    user_request: str | None = None
    workspace_id: str | None = None
    workspace_root_path: str | None = None
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
