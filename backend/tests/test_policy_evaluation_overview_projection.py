from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_record import EvaluationRecordCreate
from app.runtime.projection_registry import projection_registry
from app.services.evaluation_record_service import EvaluationRecordService
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
    evaluations = EvaluationRecordService()
    builder = PolicyEvaluationOverviewProjectionBuilderService(
        policies=policies,
        evaluations=evaluations,
        clock=clock,
    )
    service = PolicyEvaluationOverviewProjectionService(builder=builder)
    return policies, evaluations, builder, service


def create_evaluation(
    evaluations: EvaluationRecordService,
    *,
    target_id: str,
    outcome: str,
    score: float | None,
) -> str:
    record = evaluations.create_record(
        EvaluationRecordCreate(
            target_type="decision",
            target_id=target_id,
            evaluation_type="policy_review",
            outcome=outcome,  # type: ignore[arg-type]
            score=score,
            evaluator="governance",
        )
    )
    return record.evaluation_id


def test_policy_evaluation_overview_counts_runtime_linkage(tmp_path) -> None:
    generated_at = datetime(2026, 6, 17, 18, 0, tzinfo=UTC)
    policies, evaluations, builder, _ = make_fixture(
        tmp_path,
        clock=lambda: generated_at,
    )
    first_eval_id = create_evaluation(
        evaluations,
        target_id="decision-1",
        outcome="success",
        score=0.8,
    )
    second_eval_id = create_evaluation(
        evaluations,
        target_id="decision-2",
        outcome="failure",
        score=0.2,
    )
    create_evaluation(
        evaluations,
        target_id="decision-3",
        outcome="accepted",
        score=None,
    )
    create_evaluation(
        evaluations,
        target_id="decision-unlinked",
        outcome="rejected",
        score=0.1,
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
        target_id=first_eval_id,
        decision="allowed",
        reason="Direct evaluation link.",
        evaluation_id=first_eval_id,
    )
    policies.record_policy_decision(
        policy_id=evidence_policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=first_eval_id,
        decision="needs_review",
        reason="Duplicate evaluation link.",
        evaluation_id=first_eval_id,
    )
    policies.record_policy_violation(
        policy_id=evidence_policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id=second_eval_id,
        severity="warning",
        message="Result link.",
        evaluation_id=second_eval_id,
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

    first = builder.build({})
    second = builder.build({})

    assert first == second
    assert len(first) == 2
    assert first[0].metadata.projection_type == (
        POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE
    )
    assert first[0].generated_at == generated_at
    assert first_decision.created_at.isoformat() <= (
        latest_violation.created_at.isoformat()
    )

    projection_by_policy = {
        projection.policy_id: projection
        for projection in first
    }
    evidence_projection = projection_by_policy[evidence_policy.id]
    assert evidence_projection.policy_name == "Evidence policy"
    assert evidence_projection.total_evaluations == 2
    assert evidence_projection.success_count == 1
    assert evidence_projection.failure_count == 1
    assert evidence_projection.accepted_count == 0
    assert evidence_projection.average_score == 0.5
    quiet_projection = projection_by_policy[quiet_policy.id]
    assert quiet_projection.total_evaluations == 0
    assert quiet_projection.success_count == 0
    assert quiet_projection.failure_count == 0
    assert quiet_projection.average_score is None


def test_policy_evaluation_overview_route_works() -> None:
    client = TestClient(app)
    evaluation = client.post(
        "/runtime/evaluations",
        json={
            "target_type": "decision",
            "target_id": "route-decision",
            "evaluation_type": "policy_review",
            "outcome": "success",
            "score": 1.0,
            "evaluator": "governance",
        },
    ).json()
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
        target_id="route-decision",
        decision="allowed",
        reason="Route link.",
        evaluation_id=evaluation["evaluation_id"],
    )

    response = client.get("/runtime/policy-evaluation-overview")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["policy_id"] == policy.id
    assert body[0]["policy_name"] == "Route overview policy"
    assert body[0]["total_evaluations"] == 1
    assert body[0]["success_count"] == 1
    assert body[0]["average_score"] == 1.0


def test_registry_includes_policy_evaluation_overview_projection() -> None:
    assert POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
