from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.projection import Projection


ArtifactLineageStatus = Literal["linked", "orphaned", "incomplete"]


class ArtifactLineageRecord(BaseModel):
    artifact_id: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    session_id: str | None = None
    source_event_id: int = Field(ge=1)
    producing_tool_invocation_id: str | None = None
    proposal_id: str | None = None
    decision_id: str | None = None
    parent_artifact_ids: list[str]
    related_event_ids: list[int]
    created_at: datetime
    updated_at: datetime
    lineage_status: ArtifactLineageStatus
    metadata: dict[str, object] = Field(default_factory=dict)


class ArtifactLineageChain(BaseModel):
    artifact_id: str = Field(min_length=1)
    records: list[ArtifactLineageRecord]
    complete: bool


class ArtifactLineageEventSummary(BaseModel):
    event_id: int = Field(ge=1)
    event_type: str = Field(min_length=1)
    occurred_at: datetime
    severity: str = Field(min_length=1)
    message: str


class ArtifactLineageEvents(BaseModel):
    artifact_id: str = Field(min_length=1)
    events: list[ArtifactLineageEventSummary]
    event_count: int = Field(ge=0)


class ArtifactLineageMetrics(BaseModel):
    artifact_lineage_records_total: int = Field(ge=0)
    artifact_lineage_orphans_total: int = Field(ge=0)
    artifact_lineage_rebuilds_total: int = Field(ge=0)
    artifact_decision_links_total: int = Field(ge=0)
    artifact_proposal_links_total: int = Field(ge=0)
    artifact_tool_links_total: int = Field(ge=0)


class ArtifactLineageSummary(ArtifactLineageMetrics):
    total_artifacts: int = Field(ge=0)
    linked_artifacts: int = Field(ge=0)
    orphaned_artifacts: int = Field(ge=0)
    artifact_types: dict[str, int]
    producing_tools: dict[str, int]
    decision_linked_artifacts: int = Field(ge=0)
    proposal_linked_artifacts: int = Field(ge=0)
    last_lineage_update: datetime | None = None


class ArtifactLineageProjection(Projection):
    records: list[ArtifactLineageRecord]
    summary: ArtifactLineageSummary
    incomplete_event_ids: list[int] = Field(default_factory=list)
