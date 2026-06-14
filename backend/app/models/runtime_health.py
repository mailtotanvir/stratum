from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RuntimeHealthStatusValue = Literal[
    "healthy",
    "warning",
    "degraded",
    "unhealthy",
]
RuntimeHealthFindingSeverity = Literal[
    "info",
    "warning",
    "error",
    "critical",
]


class RuntimeHealthFinding(BaseModel):
    finding_id: str = Field(min_length=1)
    finding_type: str = Field(min_length=1)
    severity: RuntimeHealthFindingSeverity
    subsystem: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeSubsystemHealth(BaseModel):
    subsystem_name: str = Field(min_length=1)
    status: RuntimeHealthStatusValue
    score: int = Field(ge=0, le=100)
    findings: list[RuntimeHealthFinding] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class RuntimeHealthStatus(BaseModel):
    overall_status: RuntimeHealthStatusValue
    generated_at: datetime
    health_score: int = Field(ge=0, le=100)
    subsystem_results: list[RuntimeSubsystemHealth]
    findings: list[RuntimeHealthFinding] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
