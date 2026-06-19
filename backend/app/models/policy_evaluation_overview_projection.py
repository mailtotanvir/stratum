from datetime import datetime

from pydantic import BaseModel

from app.models.projection import Projection


class PolicyEvaluationPolicySummary(BaseModel):
    policy_id: str
    policy_name: str
    policy_type: str
    policy_status: str
    linked_decision_count: int
    linked_violation_count: int
    linked_evaluation_count: int
    latest_evidence_at: str | None = None


class PolicyEvaluationOverviewProjection(Projection):
    policy_count: int
    evaluation_count: int
    linked_policy_decision_count: int
    linked_policy_violation_count: int
    linked_evaluation_count: int
    unlinked_evaluation_count: int
    policies_with_evidence_count: int
    policies_without_evidence_count: int
    latest_policy_evidence_at: str | None = None
    generated_at: datetime
    policy_summaries: list[PolicyEvaluationPolicySummary]
