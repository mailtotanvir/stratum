from typing import Literal

from pydantic import BaseModel, Field

from app.models.agent_adapter import AgentCapabilityManifest


AgentAdapterRegistryHealthStatus = Literal["healthy", "degraded"]


class AgentAdapterCatalogEntry(BaseModel):
    manifest: AgentCapabilityManifest


class AgentAdapterCatalog(BaseModel):
    adapters: list[AgentAdapterCatalogEntry]


class AgentAdapterRegistryDiagnostics(BaseModel):
    status: AgentAdapterRegistryHealthStatus
    total_registered: int = Field(ge=0)
    duplicate_adapter_ids: list[str] = Field(default_factory=list)
    invalid_adapter_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AgentEventNormalizationCatalog(BaseModel):
    source_event_kinds: list[str]
    runtime_event_types: list[str]
    severities: list[str]
