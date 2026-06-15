from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.projection import Projection


class DecisionLineageRecord(BaseModel):
    decision_id: str = Field(min_length=1)
    session_id: str | None = None
    recommendation_id: str | None = None
    proposal_id: str | None = None
    parent_decision_id: str | None = None
    lineage_depth: int = Field(ge=0)
    selected_at: datetime
    decision_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    evidence_count: int = Field(ge=0)
    source_event_ids: list[int]
    related_artifact_ids: list[str]
    related_proposal_ids: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionLineageEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_type: str | None = None
    evidence_reference: str | None = None
    summary: str | None = None
    source_event_id: int = Field(ge=1)


class DecisionLineageEvidenceSummary(BaseModel):
    decision_id: str = Field(min_length=1)
    evidence_count: int = Field(ge=0)
    evidence: list[DecisionLineageEvidence]
    related_artifact_ids: list[str]


class DecisionLineageChain(BaseModel):
    decision_id: str = Field(min_length=1)
    records: list[DecisionLineageRecord]
    complete: bool


class DecisionLineageMetrics(BaseModel):
    decision_lineage_records_total: int = Field(ge=0)
    lineage_rebuilds_total: int = Field(ge=0)
    lineage_orphans_total: int = Field(ge=0)
    lineage_max_depth: int = Field(ge=0)
    evidence_links_total: int = Field(ge=0)


class DecisionLineageSummary(DecisionLineageMetrics):
    total_decisions: int = Field(ge=0)
    total_lineage_chains: int = Field(ge=0)
    average_lineage_depth: float = Field(ge=0)
    orphaned_decisions: int = Field(ge=0)
    evidence_linked_decisions: int = Field(ge=0)
    last_lineage_update: datetime | None = None


class DecisionLineageProjection(Projection):
    records: list[DecisionLineageRecord]
    summary: DecisionLineageSummary
    incomplete_event_ids: list[int] = Field(default_factory=list)
