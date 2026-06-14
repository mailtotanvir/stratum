from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ProjectionReplayStatus = Literal["completed", "failed"]


class ProjectionReplayRequest(BaseModel):
    projection_name: str = Field(min_length=1)
    event_id_start: int | None = Field(default=None, ge=1)
    event_id_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_event_range(self) -> "ProjectionReplayRequest":
        if (
            self.event_id_start is not None
            and self.event_id_end is not None
            and self.event_id_start > self.event_id_end
        ):
            raise ValueError(
                "event_id_start must be less than or equal to event_id_end"
            )
        return self


class ProjectionReplayResult(BaseModel):
    projection_name: str = Field(min_length=1)
    projection_version: int = Field(ge=1)
    replay_started_at: datetime
    replay_completed_at: datetime
    status: ProjectionReplayStatus
    source_event_count: int = Field(ge=0)
    applied_event_count: int = Field(ge=0)
    skipped_event_count: int = Field(ge=0)
    failed_event_count: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    dry_run: bool

