from datetime import datetime

from pydantic import BaseModel


class PolicyProjectionDiagnostics(BaseModel):
    projection_type: str
    registered: bool
    rebuildable: bool
    persisted: bool
    source: str
    route: str


class PolicyDiagnostics(BaseModel):
    policy_count: int
    policy_version_count: int
    policy_decision_count: int
    policy_violation_count: int
    policy_decisions_with_evaluation_count: int
    policy_violations_with_evaluation_count: int
    policies_without_versions_count: int
    policies_without_decisions_count: int
    policies_without_violations_count: int
    registered_projection_types: list[str]
    projections: list[PolicyProjectionDiagnostics]
    generated_at: datetime
