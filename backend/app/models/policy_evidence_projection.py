from pydantic import BaseModel

from app.models.projection import Projection


class PolicyEvidenceItem(BaseModel):
    evidence_type: str
    policy_decision_id: str | None = None
    policy_violation_id: str | None = None
    target_type: str
    target_id: str
    evaluation_id: str | None = None
    evaluation_result_id: str | None = None
    decision: str | None = None
    severity: str | None = None
    reason: str | None = None
    message: str | None = None
    created_at: str


class PolicyEvidenceProjection(Projection):
    policy_id: str
    policy_name: str
    policy_type: str
    policy_status: str
    evidence_count: int
    decision_evidence_count: int
    violation_evidence_count: int
    evaluation_ids: list[str]
    evaluation_result_ids: list[str]
    latest_evidence_at: str | None = None
    evidence_items: list[PolicyEvidenceItem]
