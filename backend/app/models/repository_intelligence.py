from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModuleMapEntry(BaseModel):
    module_name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    kind: str = Field(min_length=1)


class DependencyOverviewEntry(BaseModel):
    name: str = Field(min_length=1)
    version: str | None = None
    scope: str = Field(min_length=1)


class RuntimeInventoryEntry(BaseModel):
    name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepositoryIntelligenceSummary(BaseModel):
    repository_id: str = Field(min_length=1)
    generated_at: datetime
    architecture_summary: str
    module_map: list[ModuleMapEntry]
    service_graph: list[str]
    dependency_overview: list[DependencyOverviewEntry]
    runtime_inventory: list[RuntimeInventoryEntry]
    provider_inventory: list[RuntimeInventoryEntry]
    tool_inventory: list[RuntimeInventoryEntry]
    evidence_sources: list[str] = Field(default_factory=list)

