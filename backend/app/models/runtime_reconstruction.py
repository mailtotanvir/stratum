from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.runtime_health import RuntimeHealthStatusValue


class RuntimeReconstructionTimelineItem(BaseModel):
    event_id: int = Field(ge=1)
    occurred_at: datetime
    event_type: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    summary: str


class RuntimeReconstructionDecisionSummary(BaseModel):
    decision_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    occurred_at: datetime
    lineage_depth: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    proposal_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    complete: bool = True


class RuntimeReconstructionArtifactSummary(BaseModel):
    artifact_id: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    lineage_status: str = Field(min_length=1)
    proposal_id: str | None = None
    decision_id: str | None = None
    producing_tool_invocation_id: str | None = None
    parent_artifact_ids: list[str] = Field(default_factory=list)


class RuntimeReconstructionEvaluationResultSummary(BaseModel):
    evaluation_result_id: str = Field(min_length=1)
    dimension_id: str = Field(min_length=1)
    score: float
    rationale: str = Field(min_length=1)
    created_at: datetime


class RuntimeReconstructionEvaluationSummary(BaseModel):
    evaluation_id: str = Field(min_length=1)
    evaluation_type: str = Field(min_length=1)
    status: str = Field(min_length=1)
    created_at: datetime
    session_id: str | None = None
    decision_id: str | None = None
    artifact_id: str | None = None
    results: list[RuntimeReconstructionEvaluationResultSummary] = Field(
        default_factory=list
    )


class RuntimeReconstructionToolSummary(BaseModel):
    tool_invocation_id: str = Field(min_length=1)
    tool_id: str | None = None
    tool_name: str | None = None
    status: str = Field(min_length=1)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class RuntimeReconstructionHealthSummary(BaseModel):
    status: RuntimeHealthStatusValue
    health_score: int = Field(ge=0, le=100)
    consistency_status: str = Field(min_length=1)
    finding_count: int = Field(ge=0)
    incomplete_reason_count: int = Field(ge=0)


class RuntimeReconstructionProposalSummary(BaseModel):
    proposal_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str | None = None
    title: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class RuntimeReconstructionSessionSummary(BaseModel):
    session_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    event_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    health_status: RuntimeHealthStatusValue
    last_activity_timestamp: datetime | None = None


class RuntimeReconstructionMetrics(BaseModel):
    reconstruction_views_built_total: int = Field(ge=0)
    reconstruction_incomplete_views_total: int = Field(ge=0)
    reconstruction_failed_views_total: int = Field(ge=0)
    reconstructed_sessions_total: int = Field(ge=0)


class RuntimeReconstructionView(BaseModel):
    session_id: str = Field(min_length=1)
    session_status: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime | None = None
    total_events: int = Field(ge=0)
    warnings_count: int = Field(ge=0)
    errors_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    governance_decisions: list[RuntimeReconstructionDecisionSummary]
    proposal_summaries: list[RuntimeReconstructionProposalSummary]
    decision_lineage_summaries: list[
        RuntimeReconstructionDecisionSummary
    ]
    artifact_lineage_summaries: list[
        RuntimeReconstructionArtifactSummary
    ]
    evaluation_summaries: list[RuntimeReconstructionEvaluationSummary] = Field(
        default_factory=list
    )
    tool_execution_summaries: list[RuntimeReconstructionToolSummary]
    health_consistency_status: RuntimeReconstructionHealthSummary
    timeline: list[RuntimeReconstructionTimelineItem]
    incomplete: bool = False
    incomplete_reasons: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
