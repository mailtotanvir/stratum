from typing import Any

from pydantic import BaseModel, Field


class SessionAgentExecutionItem(BaseModel):
    agent_execution_id: str | None = None
    provider_execution_id: str | None = None
    provider: str | None = None
    model: str | None = None
    task_id: str | None = None
    correlation_id: str | None = None
    status: str = Field(min_length=1)
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    usage: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionAgentExecutionProjection(BaseModel):
    runtime_session_id: str = Field(min_length=1)
    executions: list[SessionAgentExecutionItem] = Field(default_factory=list)
    total_agent_executions: int = Field(ge=0)
    completed_agent_executions: int = Field(ge=0)
    failed_agent_executions: int = Field(ge=0)
    total_provider_executions: int = Field(ge=0)
    completed_provider_executions: int = Field(ge=0)
    failed_provider_executions: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
