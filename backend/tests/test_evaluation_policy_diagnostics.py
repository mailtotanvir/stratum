from fastapi.testclient import TestClient

from app.main import app
from app.services.evaluation_policy_diagnostics_service import (
    EvaluationPolicyDiagnosticsService,
)
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.policy_service import PolicyService, policy_service


def make_fixture(tmp_path):
    evaluations = EvaluationService(tmp_path / "evaluations.db")
    policies = PolicyService(tmp_path / "policies.db")
    service = EvaluationPolicyDiagnosticsService(
        evaluations=evaluations,
        policies=policies,
    )
    return evaluations, policies, service


def test_evaluation_policy_diagnostics_counts_runtime_state(tmp_path) -> None:
    evaluations, policies, service = make_fixture(tmp_path)
    first_eval = evaluations.create_evaluation(
        session_id="session-1",
        evaluation_type="manual_review",
        status="recorded",
    )
    second_eval = evaluations.create_evaluation(
        session_id="session-2",
        evaluation_type="manual_review",
        status="recorded",
    )
    third_eval = evaluations.create_evaluation(
        session_id="session-3",
        evaluation_type="manual_review",
        status="recorded",
    )
    dimension = evaluations.create_dimension("Quality", "Quality signal")
    second_result = evaluations.add_result(
        second_eval.id,
        dimension.id,
        0.5,
        "Below target.",
    )
    policy = policies.create_policy(
        name="Evaluation policy",
        description="Links policy activity to evaluations.",
        policy_type="evaluation",
        status="active",
    )
    quiet_policy = policies.create_policy(
        name="Quiet policy",
        description="No policy activity.",
        policy_type="runtime",
        status="draft",
    )
    version = policies.add_policy_version(policy.id, 1, {"mode": "observe"})
    policies.add_policy_version(quiet_policy.id, 1, {"mode": "observe"})
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=first_eval.id,
        decision="allowed",
        reason="Direct evaluation link.",
        evaluation_id=first_eval.id,
    )
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="unknown-evaluation",
        decision="needs_review",
        reason="Unknown attribution.",
        evaluation_id="unknown-evaluation",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id=second_result.id,
        severity="warning",
        message="Result evidence link.",
        evaluation_result_id=second_result.id,
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="unlinked-policy-target",
        severity="critical",
        message="No evaluation link.",
    )

    diagnostics = service.generate()

    assert diagnostics.evaluation_count == 3
    assert diagnostics.evaluation_result_count == 1
    assert diagnostics.policy_count == 2
    assert diagnostics.policy_version_count == 2
    assert diagnostics.policy_decision_count == 2
    assert diagnostics.policy_violation_count == 2
    assert diagnostics.linked_policy_decision_count == 2
    assert diagnostics.linked_policy_violation_count == 1
    assert diagnostics.linked_evaluation_count == 2
    assert diagnostics.unlinked_evaluation_count == 1
    assert third_eval.id not in {first_eval.id, second_eval.id}


def test_evaluation_policy_diagnostics_reports_projection_registration(
    tmp_path,
) -> None:
    _, _, service = make_fixture(tmp_path)

    diagnostics = service.generate()

    assert diagnostics.registered_evaluation_projection_types == [
        "evaluation_outcome_rollup",
        "evaluation_summary",
        "evaluation_trend",
    ]
    assert diagnostics.registered_policy_projection_types == [
        "policy_evaluation_overview",
        "policy_evidence",
        "policy_summary",
    ]
    assert diagnostics.missing_expected_projection_types == []


def test_evaluation_policy_diagnostics_route_works() -> None:
    evaluation = evaluation_service.create_evaluation(
        session_id="route-session",
        evaluation_type="manual_review",
        status="recorded",
    )
    policy = policy_service.create_policy(
        name="Route evaluation policy",
        description="Links through route diagnostics.",
        policy_type="evaluation",
        status="active",
    )
    version = policy_service.add_policy_version(policy.id, 1, {"mode": "observe"})
    policy_service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=evaluation.id,
        decision="allowed",
        reason="Route link.",
        evaluation_id=evaluation.id,
    )

    response = TestClient(app).get("/runtime/evaluation-policy-diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_count"] == 1
    assert body["evaluation_result_count"] == 0
    assert body["policy_count"] == 1
    assert body["policy_version_count"] == 1
    assert body["policy_decision_count"] == 1
    assert body["policy_violation_count"] == 0
    assert body["linked_policy_decision_count"] == 1
    assert body["linked_policy_violation_count"] == 0
    assert body["linked_evaluation_count"] == 1
    assert body["unlinked_evaluation_count"] == 0
    assert body["missing_expected_projection_types"] == []
