from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProjectionRebuildStatus = Literal["started", "completed", "failed"]


class ProjectionRebuildRecord(BaseModel):
    projection_name: str = Field(min_length=1)
    projection_version: int = Field(ge=1)
    rebuild_started_at: datetime
    rebuild_completed_at: datetime | None = None
    status: ProjectionRebuildStatus
    source_event_count: int = Field(ge=0)
    source_event_range_start: int | None = Field(default=None, ge=1)
    source_event_range_end: int | None = Field(default=None, ge=1)
    duration_ms: float | None = Field(default=None, ge=0)


class ProjectionLifecycleStatus(BaseModel):
    projection_name: str = Field(min_length=1)
    projection_version: int = Field(ge=1)
    latest_rebuild_status: ProjectionRebuildStatus | None = None
    latest_rebuild_started_at: datetime | None = None
    latest_rebuild_completed_at: datetime | None = None
    latest_rebuild_duration_ms: float | None = Field(
        default=None,
        ge=0,
    )


class ProjectionRebuildHistory(BaseModel):
    rebuilds: list[ProjectionRebuildRecord]
    total_count: int = Field(ge=0)

