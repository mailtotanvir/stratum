from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RuntimeHealthStatusValue = Literal[
    "healthy",
    "degraded",
    "warning",
    "unhealthy",
]


class RuntimeSubsystemHealth(BaseModel):
    subsystem_name: str = Field(min_length=1)
    status: RuntimeHealthStatusValue
    score: int = Field(ge=0, le=100)
    findings: list[dict[str, Any]]
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class RuntimeHealthStatus(BaseModel):
    overall_status: RuntimeHealthStatusValue
    generated_at: datetime
    health_score: int = Field(ge=0, le=100)
    subsystem_results: list[RuntimeSubsystemHealth]
    diagnostics: list[dict[str, Any]]
