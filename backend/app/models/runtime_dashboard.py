from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RuntimeDashboardSection(BaseModel):
    section_name: str = Field(min_length=1)
    section_version: int = Field(ge=1)
    generated_at: datetime
    summary: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeDashboard(BaseModel):
    generated_at: datetime
    runtime_summary: RuntimeDashboardSection
    session_summary: RuntimeDashboardSection
    decision_summary: RuntimeDashboardSection
    projection_summary: RuntimeDashboardSection
    query_summary: RuntimeDashboardSection
    governance_summary: RuntimeDashboardSection
    diagnostics_summary: RuntimeDashboardSection
    health_summary: RuntimeDashboardSection
