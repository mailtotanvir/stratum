from pydantic import BaseModel

from app.models.projection import Projection


class PolicyDecisionSummary(BaseModel):
    decision: str
    count: int


class PolicyViolationSummary(BaseModel):
    severity: str
    count: int


class PolicySummaryProjection(Projection):
    policy_id: str
    name: str
    description: str
    policy_type: str
    status: str
    latest_version: int | None = None
    version_count: int
    decision_count: int
    violation_count: int
    evaluation_linked_decision_count: int
    evaluation_linked_violation_count: int
    latest_decision_at: str | None = None
    latest_violation_at: str | None = None
    decision_summary: list[PolicyDecisionSummary]
    violation_summary: list[PolicyViolationSummary]
    created_at: str
    updated_at: str
