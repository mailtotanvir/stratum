from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_record import EvaluationRecordCreate
from app.runtime.projection_registry import projection_registry
from app.services.evaluation_record_service import EvaluationRecordService
from app.services.policy_evaluation_overview_projection_builder_service import (
    POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
    PolicyEvaluationOverviewProjectionBuilderService,
    policy_evaluation_overview_projection_builder_service,
)
from app.services.policy_service import PolicyService, policy_service


def create_evaluation(
    service: EvaluationRecordService,
    *,
    target_id: str,
    outcome: str,
    score: float | None,
) -> str:
    record = service.create_record(
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


def create_policy(policies: PolicyService, name: str):
    policy = policies.create_policy(
        name=name,
        description=f"{name} description.",
        policy_type="evaluation",
        status="active",
    )
    version = policies.add_policy_version(policy.id, 1, {"mode": "observe"})
    return policy, version


def test_policy_evaluation_overview_builds_deterministically(tmp_path) -> None:
    generated_at = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
    policies = PolicyService(tmp_path / "policies.db")
    evaluations = EvaluationRecordService()
    builder = PolicyEvaluationOverviewProjectionBuilderService(
        policies=policies,
        evaluations=evaluations,
        clock=lambda: generated_at,
    )
    first_policy, first_version = create_policy(policies, "Quality policy")
    second_policy, second_version = create_policy(policies, "Safety policy")
    success_id = create_evaluation(
        evaluations,
        target_id="decision-1",
        outcome="success",
        score=0.8,
    )
    failure_id = create_evaluation(
        evaluations,
        target_id="decision-2",
        outcome="failure",
        score=0.2,
    )
    accepted_id = create_evaluation(
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
    policies.record_policy_decision(
        policy_id=first_policy.id,
        policy_version_id=first_version.id,
        target_type="decision",
        target_id="decision-1",
        decision="allowed",
        reason="Linked success.",
        evaluation_id=success_id,
    )
    policies.record_policy_violation(
        policy_id=first_policy.id,
        policy_version_id=first_version.id,
        target_type="decision",
        target_id="decision-2",
        severity="warning",
        message="Linked failure.",
        evaluation_id=failure_id,
    )
    policies.record_policy_decision(
        policy_id=first_policy.id,
        policy_version_id=first_version.id,
        target_type="decision",
        target_id="decision-1",
        decision="allowed",
        reason="Duplicate link should not double count.",
        evaluation_id=success_id,
    )
    policies.record_policy_decision(
        policy_id=second_policy.id,
        policy_version_id=second_version.id,
        target_type="decision",
        target_id="decision-3",
        decision="allowed",
        reason="Linked accepted.",
        evaluation_id=accepted_id,
    )
    policies.record_policy_violation(
        policy_id=second_policy.id,
        policy_version_id=second_version.id,
        target_type="decision",
        target_id="missing",
        severity="critical",
        message="Missing evaluation is ignored.",
        evaluation_id="missing-evaluation",
    )

    first = builder.build({})
    second = builder.build({})

    assert first == second
    assert [projection.policy_id for projection in first] == [
        first_policy.id,
        second_policy.id,
    ]
    quality = first[0]
    assert quality.metadata.projection_type == (
        POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE
    )
    assert quality.generated_at == generated_at
    assert quality.policy_name == "Quality policy"
    assert quality.total_evaluations == 2
    assert quality.success_count == 1
    assert quality.failure_count == 1
    assert quality.accepted_count == 0
    assert quality.rejected_count == 0
    assert quality.reverted_count == 0
    assert quality.inconclusive_count == 0
    assert quality.average_score == 0.5

    safety = first[1]
    assert safety.policy_id == second_policy.id
    assert safety.total_evaluations == 1
    assert safety.accepted_count == 1
    assert safety.average_score is None


def test_policy_evaluation_overview_empty_states(tmp_path) -> None:
    policies = PolicyService(tmp_path / "policies.db")
    evaluations = EvaluationRecordService()
    builder = PolicyEvaluationOverviewProjectionBuilderService(
        policies=policies,
        evaluations=evaluations,
    )

    assert builder.build({}) == []

    policy, _ = create_policy(policies, "Quiet policy")
    projections = builder.build({})

    assert len(projections) == 1
    assert projections[0].policy_id == policy.id
    assert projections[0].total_evaluations == 0
    assert projections[0].success_count == 0
    assert projections[0].failure_count == 0
    assert projections[0].average_score is None


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
    policy, version = create_policy(policy_service, "Route policy")
    policy_service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="decision",
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
    assert body[0]["policy_name"] == "Route policy"
    assert body[0]["total_evaluations"] == 1
    assert body[0]["success_count"] == 1
    assert body[0]["average_score"] == 1.0


def test_policy_evaluation_overview_is_registered_and_discoverable() -> None:
    assert POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
    assert (
        projection_registry.get(POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE)
        is policy_evaluation_overview_projection_builder_service
    )
    schema = projection_registry.get_schema(
        POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE
    )
    assert schema.builder_name == "PolicyEvaluationOverviewProjectionBuilderService"
    assert schema.reconstruction.authoritative_source == (
        "policies/policy_decisions/policy_violations/"
        "runtime_evaluation_records"
    )

    response = TestClient(app).get(
        "/runtime/projections/registry/policy_evaluation_overview"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "/runtime/policy-evaluation-overview"
