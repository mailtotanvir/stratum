from typing import Any

from pydantic import BaseModel, Field


class AgentExecutionDiagnostics(BaseModel):
    agent_execution_service_ready: bool
    provider_execution_service_ready: bool
    provider_diagnostics_available: bool
    supported_agent_modes: list[str]
    supported_agent_statuses: list[str]
    mock_provider_available: bool
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
