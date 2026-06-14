from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProjectionDriftStatus = Literal[
    "in_sync",
    "drifted",
    "unavailable",
    "failed",
]


class ProjectionDriftResult(BaseModel):
    projection_name: str = Field(min_length=1)
    projection_version: int = Field(ge=1)
    checked_at: datetime
    status: ProjectionDriftStatus
    drift_detected: bool
    source_event_count: int = Field(ge=0)
    persisted_projection_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    replay_projection_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    mismatch_summary: list[str] = Field(default_factory=list)
    duration_ms: float = Field(ge=0)


class ProjectionDriftReport(BaseModel):
    projections: list[ProjectionDriftResult]
    projection_count: int = Field(ge=0)
    drifted_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)

