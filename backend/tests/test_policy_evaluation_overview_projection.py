from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.policy_evaluation_overview_projection_builder_service import (
    POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
    PolicyEvaluationOverviewProjectionBuilderService,
)
from app.services.policy_evaluation_overview_projection_service import (
    PolicyEvaluationOverviewProjectionService,
)
from app.services.policy_service import PolicyService, policy_service


def make_fixture(tmp_path, clock=None):
    policies = PolicyService(tmp_path / "policies.db")
    evaluations = EvaluationService(tmp_path / "evaluations.db")
    builder = PolicyEvaluationOverviewProjectionBuilderService(
        policies=policies,
        evaluations=evaluations,
        clock=clock,
    )
    service = PolicyEvaluationOverviewProjectionService(builder=builder)
    return policies, evaluations, builder, service


def test_policy_evaluation_overview_counts_runtime_linkage(tmp_path) -> None:
    generated_at = datetime(2026, 6, 17, 18, 0, tzinfo=UTC)
    policies, evaluations, builder, _ = make_fixture(
        tmp_path,
        clock=lambda: generated_at,
    )
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
    evidence_policy = policies.create_policy(
        name="Evidence policy",
        description="Has linked policy evidence.",
        policy_type="evaluation",
        status="active",
    )
    quiet_policy = policies.create_policy(
        name="Quiet policy",
        description="Has no linked policy evidence.",
        policy_type="runtime",
        status="draft",
    )
    version = policies.add_policy_version(
        evidence_policy.id,
        1,
        {"mode": "observe"},
    )
    policies.add_policy_version(quiet_policy.id, 1, {"mode": "observe"})
    first_decision = policies.record_policy_decision(
        policy_id=evidence_policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=first_eval.id,
        decision="allowed",
        reason="Direct evaluation link.",
        evaluation_id=first_eval.id,
    )
    policies.record_policy_decision(
        policy_id=evidence_policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=first_eval.id,
        decision="needs_review",
        reason="Duplicate evaluation link.",
        evaluation_id=first_eval.id,
    )
    policies.record_policy_violation(
        policy_id=evidence_policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id=second_result.id,
        severity="warning",
        message="Result link.",
        evaluation_result_id=second_result.id,
    )
    latest_violation = policies.record_policy_violation(
        policy_id=evidence_policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="unknown-evaluation",
        severity="critical",
        message="Unknown attribution remains policy evidence.",
        evaluation_id="unknown-evaluation",
    )

    overview = builder.build({})

    assert overview.metadata.projection_type == (
        POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE
    )
    assert overview.generated_at == generated_at
    assert overview.policy_count == 2
    assert overview.evaluation_count == 3
    assert overview.linked_policy_decision_count == 2
    assert overview.linked_policy_violation_count == 2
    assert overview.linked_evaluation_count == 2
    assert overview.unlinked_evaluation_count == 1
    assert overview.policies_with_evidence_count == 1
    assert overview.policies_without_evidence_count == 1
    assert overview.latest_policy_evidence_at == (
        latest_violation.created_at.isoformat()
    )
    assert first_decision.created_at.isoformat() <= (
        overview.latest_policy_evidence_at
    )

    summary_by_policy = {
        summary.policy_id: summary
        for summary in overview.policy_summaries
    }
    evidence_summary = summary_by_policy[evidence_policy.id]
    assert evidence_summary.policy_name == "Evidence policy"
    assert evidence_summary.linked_decision_count == 2
    assert evidence_summary.linked_violation_count == 2
    assert evidence_summary.linked_evaluation_count == 2
    assert evidence_summary.latest_evidence_at == (
        latest_violation.created_at.isoformat()
    )
    quiet_summary = summary_by_policy[quiet_policy.id]
    assert quiet_summary.linked_decision_count == 0
    assert quiet_summary.linked_violation_count == 0
    assert quiet_summary.linked_evaluation_count == 0
    assert quiet_summary.latest_evidence_at is None
    assert third_eval.id not in {first_eval.id, second_eval.id}


def test_policy_evaluation_overview_route_works() -> None:
    evaluation = evaluation_service.create_evaluation(
        session_id="route-session",
        evaluation_type="manual_review",
        status="recorded",
    )
    policy = policy_service.create_policy(
        name="Route overview policy",
        description="Visible through overview route.",
        policy_type="evaluation",
        status="active",
    )
    version = policy_service.add_policy_version(
        policy.id,
        1,
        {"mode": "observe"},
    )
    policy_service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=evaluation.id,
        decision="allowed",
        reason="Route link.",
        evaluation_id=evaluation.id,
    )

    response = TestClient(app).get("/runtime/policy-evaluation-overview")

    assert response.status_code == 200
    body = response.json()
    assert body["policy_count"] == 1
    assert body["evaluation_count"] == 1
    assert body["linked_policy_decision_count"] == 1
    assert body["linked_policy_violation_count"] == 0
    assert body["linked_evaluation_count"] == 1
    assert body["unlinked_evaluation_count"] == 0
    assert body["policies_with_evidence_count"] == 1
    assert body["policies_without_evidence_count"] == 0
    assert body["policy_summaries"][0]["policy_id"] == policy.id


def test_registry_includes_policy_evaluation_overview_projection() -> None:
    assert POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
