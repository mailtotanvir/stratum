from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.policy_projection_builder_service import (
    POLICY_SUMMARY_PROJECTION_TYPE,
    PolicyProjectionBuilderService,
)
from app.services.policy_projection_service import PolicyProjectionService
from app.services.policy_service import PolicyService, policy_service


def make_fixture(tmp_path, clock=None):
    policies = PolicyService(tmp_path / "policies.db")
    builder = PolicyProjectionBuilderService(policies=policies, clock=clock)
    service = PolicyProjectionService(builder=builder)
    return policies, builder, service


def test_policy_summary_generation_aggregates_versions_decisions_and_violations(
    tmp_path,
) -> None:
    built_at = datetime(2026, 6, 17, 16, 30, tzinfo=UTC)
    policies, builder, _ = make_fixture(tmp_path, clock=lambda: built_at)
    policy = policies.create_policy(
        name="Artifact quality policy",
        description="Summarizes observed quality policy activity.",
        policy_type="quality",
        status="active",
    )
    first_version = policies.add_policy_version(
        policy_id=policy.id,
        version=1,
        rule_payload={"mode": "observe"},
    )
    latest_version = policies.add_policy_version(
        policy_id=policy.id,
        version=3,
        rule_payload={"mode": "observe", "threshold": 0.8},
    )
    first_decision = policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=first_version.id,
        target_type="artifact",
        target_id="artifact-1",
        decision="allowed",
        reason="Observation matched.",
    )
    latest_decision = policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=latest_version.id,
        target_type="artifact",
        target_id="artifact-2",
        decision="allowed",
        reason="Observation matched again.",
        evaluation_id="evaluation-1",
    )
    latest_decision = policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=latest_version.id,
        target_type="artifact",
        target_id="artifact-3",
        decision="needs_review",
        reason="Observation needs human review.",
        evaluation_result_id="result-1",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=first_version.id,
        target_type="evaluation",
        target_id="evaluation-1",
        severity="warning",
        message="Score below target.",
    )
    latest_violation = policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=latest_version.id,
        target_type="evaluation",
        target_id="evaluation-2",
        severity="critical",
        message="Repeated score below target.",
        evaluation_id="evaluation-2",
    )

    summaries = builder.build({})

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.metadata.projection_type == POLICY_SUMMARY_PROJECTION_TYPE
    assert summary.metadata.built_at == built_at
    assert summary.metadata.reconstruction.rebuildable is True
    assert summary.metadata.reconstruction.authoritative_source == (
        "policies/policy_versions/policy_decisions/policy_violations"
    )
    assert summary.policy_id == policy.id
    assert summary.name == "Artifact quality policy"
    assert summary.policy_type == "quality"
    assert summary.status == "active"
    assert summary.latest_version == 3
    assert summary.version_count == 2
    assert summary.decision_count == 3
    assert summary.violation_count == 2
    assert summary.evaluation_linked_decision_count == 2
    assert summary.evaluation_linked_violation_count == 1
    assert summary.latest_decision_at == latest_decision.created_at.isoformat()
    assert first_decision.created_at.isoformat() <= summary.latest_decision_at
    assert summary.latest_violation_at == (
        latest_violation.created_at.isoformat()
    )
    assert [item.model_dump() for item in summary.decision_summary] == [
        {"decision": "allowed", "count": 2},
        {"decision": "needs_review", "count": 1},
    ]
    assert [item.model_dump() for item in summary.violation_summary] == [
        {"severity": "critical", "count": 1},
        {"severity": "warning", "count": 1},
    ]


def test_policy_summary_handles_policy_without_activity(tmp_path) -> None:
    policies, _, service = make_fixture(tmp_path)
    policy = policies.create_policy(
        name="Draft policy",
        description="No versions or observations yet.",
        policy_type="runtime",
        status="draft",
    )

    summary = service.get_policy_summary(policy.id)

    assert summary.latest_version is None
    assert summary.version_count == 0
    assert summary.decision_count == 0
    assert summary.violation_count == 0
    assert summary.evaluation_linked_decision_count == 0
    assert summary.evaluation_linked_violation_count == 0
    assert summary.latest_decision_at is None
    assert summary.latest_violation_at is None
    assert summary.decision_summary == []
    assert summary.violation_summary == []


def test_policy_projection_filters_by_policy_type_and_status(tmp_path) -> None:
    policies, _, service = make_fixture(tmp_path)
    active_runtime = policies.create_policy(
        name="Runtime active",
        description="Active runtime policy.",
        policy_type="runtime",
        status="active",
    )
    policies.create_policy(
        name="Runtime draft",
        description="Draft runtime policy.",
        policy_type="runtime",
        status="draft",
    )
    policies.create_policy(
        name="Quality active",
        description="Active quality policy.",
        policy_type="quality",
        status="active",
    )

    summaries = service.list_policy_summaries(
        policy_type="runtime",
        status="active",
    )

    assert [summary.policy_id for summary in summaries] == [active_runtime.id]


def test_policy_projection_routes_list_and_detail() -> None:
    policy = policy_service.create_policy(
        name="Route projection policy",
        description="Visible through projection routes.",
        policy_type="runtime",
        status="active",
    )
    version = policy_service.add_policy_version(
        policy_id=policy.id,
        version=2,
        rule_payload={"mode": "observe"},
    )
    policy_service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-route",
        decision="allowed",
        reason="Recorded.",
        evaluation_id="evaluation-route",
    )
    policy_service.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-route",
        severity="warning",
        message="Recorded.",
        evaluation_result_id="result-route",
    )

    client = TestClient(app)
    listed = client.get(
        "/runtime/policy-projections?policy_type=runtime&status=active"
    )
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["policy_id"] == policy.id
    assert body[0]["latest_version"] == 2
    assert body[0]["decision_count"] == 1
    assert body[0]["violation_count"] == 1
    assert body[0]["evaluation_linked_decision_count"] == 1
    assert body[0]["evaluation_linked_violation_count"] == 1

    detail = client.get(f"/runtime/policy-projections/{policy.id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["policy_id"] == policy.id
    assert detail_body["decision_summary"] == [
        {"decision": "allowed", "count": 1}
    ]
    assert detail_body["violation_summary"] == [
        {"severity": "warning", "count": 1}
    ]


def test_policy_projection_route_returns_not_found_for_missing_policy() -> None:
    response = TestClient(app).get("/runtime/policy-projections/missing-policy")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Policy summary not found: missing-policy"
    }


def test_registry_includes_policy_summary_projection() -> None:
    assert POLICY_SUMMARY_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
