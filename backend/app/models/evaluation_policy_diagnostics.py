from datetime import datetime

from pydantic import BaseModel


class EvaluationPolicyDiagnostics(BaseModel):
    evaluation_count: int
    evaluation_result_count: int
    policy_count: int
    policy_version_count: int
    policy_decision_count: int
    policy_violation_count: int
    linked_policy_decision_count: int
    linked_policy_violation_count: int
    linked_evaluation_count: int
    unlinked_evaluation_count: int
    registered_evaluation_projection_types: list[str]
    registered_policy_projection_types: list[str]
    missing_expected_projection_types: list[str]
    generated_at: datetime
