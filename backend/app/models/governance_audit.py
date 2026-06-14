from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.projection import Projection


class GovernanceAuditRecord(BaseModel):
    decision_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    session_id: str | None = None
    source_event_id: int = Field(ge=1)
    occurred_at: datetime
    actor: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    evidence_count: int = Field(ge=0)
    policy_reference: str | None = None
    budget_reference: str | None = None
    reflection_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceAuditMetrics(BaseModel):
    governance_records_total: int = Field(ge=0)
    approvals_total: int = Field(ge=0)
    rejections_total: int = Field(ge=0)
    policy_evaluations_total: int = Field(ge=0)
    reflection_triggers_total: int = Field(ge=0)
    budget_actions_total: int = Field(ge=0)


class GovernanceAuditSummary(GovernanceAuditMetrics):
    total_decisions: int = Field(ge=0)
    approvals: int = Field(ge=0)
    rejections: int = Field(ge=0)
    policy_evaluations: int = Field(ge=0)
    reflection_triggers: int = Field(ge=0)
    budget_actions: int = Field(ge=0)
    last_governance_activity_timestamp: datetime | None = None


class GovernanceAuditProjection(Projection):
    records: list[GovernanceAuditRecord]
    summary: GovernanceAuditSummary

