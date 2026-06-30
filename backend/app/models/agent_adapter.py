from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentAdapterTransport(StrEnum):
    HOSTED = "hosted"
    LOCAL = "local"
    MCP = "mcp"
    A2A = "a2a"
    CUSTOM = "custom"


class AgentCapabilityManifest(BaseModel):
    adapter_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    version: str | None = Field(default=None, min_length=1)
    description: str | None = None
    transport: AgentAdapterTransport = AgentAdapterTransport.CUSTOM
    provider_family: str | None = Field(default=None, min_length=1)
    supported_agent_types: list[str] = Field(default_factory=list)
    supported_capabilities: list[str] = Field(default_factory=list)
    supported_modalities: list[str] = Field(default_factory=list)
    supports_streaming: bool = False
    supports_tool_use: bool = False
    supports_approvals: bool = False
    supports_multi_agent: bool = False
    supports_memory: bool = False
    supports_artifacts: bool = False
    supports_observability: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "adapter_id",
        "display_name",
        "version",
        "provider_family",
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def normalize_lists(self) -> "AgentCapabilityManifest":
        self.supported_agent_types = _normalized_unique_list(
            self.supported_agent_types
        )
        self.supported_capabilities = _normalized_unique_list(
            self.supported_capabilities
        )
        self.supported_modalities = _normalized_unique_list(
            self.supported_modalities
        )
        return self


class AgentInvocation(BaseModel):
    adapter_id: str = Field(min_length=1)
    invocation_id: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    user_request: str = Field(min_length=1)
    instructions: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "adapter_id",
        "invocation_id",
        "session_id",
        "task_id",
        "correlation_id",
        "user_request",
        "instructions",
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def normalize_capabilities(self) -> "AgentInvocation":
        self.capabilities = _normalized_unique_list(self.capabilities)
        return self


class AgentInvocationResult(BaseModel):
    invocation_id: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    output: str | None = None
    summary: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)

    @field_validator("invocation_id", "adapter_id", "status", "error_type", "error_message")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentEventBridgeEvent(BaseModel):
    source_event_type: str = Field(min_length=1)
    runtime_event_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: str = Field(default="info", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_event_type", "runtime_event_type", "message", "severity")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


def _normalized_unique_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value.strip():
            raise ValueError("must not contain blank entries")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
