from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ExplanationSubjectType = Literal["decision", "artifact", "session"]


class EvidenceExplanation(BaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_type: str | None = None
    evidence_reference: str | None = None
    summary: str | None = None
    source_event_id: int = Field(ge=1)


class GovernanceExplanation(BaseModel):
    decision_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    occurred_at: datetime
    evidence_count: int = Field(ge=0)
    policy_reference: str | None = None
    budget_reference: str | None = None
    reflection_reference: str | None = None
    source_event_id: int = Field(ge=1)


class ArtifactExplanation(BaseModel):
    artifact_id: str = Field(min_length=1)
    artifact_path: str | None = None
    artifact_type: str | None = None
    lineage_status: str = Field(min_length=1)
    decision_id: str | None = None
    proposal_id: str | None = None
    producing_tool_invocation_id: str | None = None
    parent_artifact_ids: list[str] = Field(default_factory=list)
    related_event_ids: list[int] = Field(default_factory=list)
    complete: bool = True
    incomplete_reasons: list[str] = Field(default_factory=list)


class DecisionExplanation(BaseModel):
    decision_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    recommendation_source: str | None = None
    proposal_source: str | None = None
    governance_actions: list[GovernanceExplanation] = Field(
        default_factory=list
    )
    evidence_summary: list[EvidenceExplanation] = Field(default_factory=list)
    related_artifacts: list[ArtifactExplanation] = Field(default_factory=list)
    lineage_depth: int = Field(ge=0)
    complete: bool = True
    incomplete_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class ExplanationView(BaseModel):
    generated_at: datetime
    subject_type: ExplanationSubjectType
    subject_id: str = Field(min_length=1)
    decisions: list[DecisionExplanation] = Field(default_factory=list)
    artifacts: list[ArtifactExplanation] = Field(default_factory=list)
    governance_actions: list[GovernanceExplanation] = Field(default_factory=list)
    evidence: list[EvidenceExplanation] = Field(default_factory=list)
    complete: bool = True
    incomplete_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
