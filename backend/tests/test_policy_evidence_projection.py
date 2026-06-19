from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.policy_evidence_projection_builder_service import (
    POLICY_EVIDENCE_PROJECTION_TYPE,
    PolicyEvidenceProjectionBuilderService,
)
from app.services.policy_evidence_projection_service import (
    PolicyEvidenceProjectionService,
)
from app.services.policy_service import PolicyService, policy_service


def make_fixture(tmp_path, clock=None):
    policies = PolicyService(tmp_path / "policies.db")
    builder = PolicyEvidenceProjectionBuilderService(
        policies=policies,
        clock=clock,
    )
    service = PolicyEvidenceProjectionService(builder=builder)
    return policies, builder, service


def test_policy_evidence_includes_only_evaluation_linked_records(
    tmp_path,
) -> None:
    built_at = datetime(2026, 6, 17, 17, 0, tzinfo=UTC)
    policies, builder, _ = make_fixture(tmp_path, clock=lambda: built_at)
    policy = policies.create_policy(
        name="Evidence policy",
        description="Policy with evaluation evidence.",
        policy_type="evaluation",
        status="active",
    )
    version = policies.add_policy_version(policy.id, 1, {"mode": "observe"})
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-unlinked",
        decision="allowed",
        reason="No evaluation evidence.",
    )
    decision = policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-linked",
        decision="needs_review",
        reason="Evaluation evidence linked.",
        evaluation_id="evaluation-1",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-unlinked",
        severity="warning",
        message="No evaluation evidence.",
    )
    violation = policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-linked",
        severity="critical",
        message="Evaluation result evidence linked.",
        evaluation_result_id="result-1",
    )

    projections = builder.build({})

    assert len(projections) == 1
    projection = projections[0]
    assert projection.metadata.projection_type == POLICY_EVIDENCE_PROJECTION_TYPE
    assert projection.metadata.built_at == built_at
    assert projection.policy_id == policy.id
    assert projection.policy_name == "Evidence policy"
    assert projection.policy_type == "evaluation"
    assert projection.policy_status == "active"
    assert projection.evidence_count == 2
    assert projection.decision_evidence_count == 1
    assert projection.violation_evidence_count == 1
    assert projection.evaluation_ids == ["evaluation-1"]
    assert projection.evaluation_result_ids == ["result-1"]
    assert projection.latest_evidence_at == violation.created_at.isoformat()
    assert [
        (item.evidence_type, item.policy_decision_id, item.policy_violation_id)
        for item in projection.evidence_items
    ] == [
        ("decision", decision.id, None),
        ("violation", None, violation.id),
    ]
    decision_item = projection.evidence_items[0]
    assert decision_item.evaluation_id == "evaluation-1"
    assert decision_item.decision == "needs_review"
    assert decision_item.reason == "Evaluation evidence linked."
    violation_item = projection.evidence_items[1]
    assert violation_item.evaluation_result_id == "result-1"
    assert violation_item.severity == "critical"
    assert violation_item.message == "Evaluation result evidence linked."


def test_policy_evidence_groups_by_policy_id_and_collects_unique_ids(
    tmp_path,
) -> None:
    policies, _, service = make_fixture(tmp_path)
    first_policy = policies.create_policy(
        name="First policy",
        description="First.",
        policy_type="evaluation",
        status="active",
    )
    second_policy = policies.create_policy(
        name="Second policy",
        description="Second.",
        policy_type="evaluation",
        status="active",
    )
    first_version = policies.add_policy_version(
        first_policy.id,
        1,
        {"mode": "observe"},
    )
    second_version = policies.add_policy_version(
        second_policy.id,
        1,
        {"mode": "observe"},
    )
    policies.record_policy_decision(
        policy_id=first_policy.id,
        policy_version_id=first_version.id,
        target_type="evaluation",
        target_id="evaluation-1",
        decision="allowed",
        reason="Linked.",
        evaluation_id="evaluation-1",
    )
    policies.record_policy_violation(
        policy_id=first_policy.id,
        policy_version_id=first_version.id,
        target_type="evaluation",
        target_id="evaluation-1",
        severity="warning",
        message="Linked.",
        evaluation_id="evaluation-1",
        evaluation_result_id="result-1",
    )
    policies.record_policy_decision(
        policy_id=second_policy.id,
        policy_version_id=second_version.id,
        target_type="evaluation_result",
        target_id="result-2",
        decision="needs_review",
        reason="Linked.",
        evaluation_result_id="result-2",
    )

    projections = service.list_policy_evidence()

    assert [projection.policy_id for projection in projections] == [
        first_policy.id,
        second_policy.id,
    ]
    first = projections[0]
    assert first.evidence_count == 2
    assert first.evaluation_ids == ["evaluation-1"]
    assert first.evaluation_result_ids == ["result-1"]
    second = projections[1]
    assert second.evidence_count == 1
    assert second.evaluation_ids == []
    assert second.evaluation_result_ids == ["result-2"]


def test_policy_evidence_filters_by_evaluation_id_and_evidence_type(
    tmp_path,
) -> None:
    policies, _, service = make_fixture(tmp_path)
    policy = policies.create_policy(
        name="Filter policy",
        description="Filterable evidence.",
        policy_type="evaluation",
        status="active",
    )
    version = policies.add_policy_version(policy.id, 1, {"mode": "observe"})
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-filter",
        decision="allowed",
        reason="Linked decision.",
        evaluation_id="evaluation-filter",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-filter",
        severity="warning",
        message="Linked violation.",
        evaluation_id="evaluation-filter",
    )
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-other",
        decision="needs_review",
        reason="Other evidence.",
        evaluation_id="evaluation-other",
    )

    filtered = service.list_policy_evidence(
        evaluation_id="evaluation-filter",
        evidence_type="decision",
    )

    assert len(filtered) == 1
    assert filtered[0].policy_id == policy.id
    assert filtered[0].evidence_count == 1
    assert filtered[0].decision_evidence_count == 1
    assert filtered[0].violation_evidence_count == 0
    assert filtered[0].evidence_items[0].evidence_type == "decision"
    assert filtered[0].evidence_items[0].evaluation_id == "evaluation-filter"


def test_policy_evidence_filters_by_target_and_result_id(tmp_path) -> None:
    policies, _, service = make_fixture(tmp_path)
    policy = policies.create_policy(
        name="Target filter policy",
        description="Filterable target evidence.",
        policy_type="evaluation",
        status="active",
    )
    version = policies.add_policy_version(policy.id, 1, {"mode": "observe"})
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-1",
        decision="allowed",
        reason="Linked decision.",
        evaluation_result_id="result-1",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-2",
        severity="warning",
        message="Linked violation.",
        evaluation_result_id="result-2",
    )

    filtered = service.list_policy_evidence(
        evaluation_result_id="result-1",
        target_type="artifact",
        target_id="artifact-1",
    )

    assert len(filtered) == 1
    assert filtered[0].evidence_count == 1
    assert filtered[0].evidence_items[0].evaluation_result_id == "result-1"
    assert filtered[0].evidence_items[0].target_id == "artifact-1"


def test_policy_evidence_routes_list_and_detail() -> None:
    policy = policy_service.create_policy(
        name="Route evidence policy",
        description="Visible through evidence routes.",
        policy_type="evaluation",
        status="active",
    )
    version = policy_service.add_policy_version(
        policy_id=policy.id,
        version=1,
        rule_payload={"mode": "observe"},
    )
    policy_service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-route",
        decision="allowed",
        reason="Linked route evidence.",
        evaluation_id="evaluation-route",
    )
    policy_service.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id="result-route",
        severity="warning",
        message="Linked route result.",
        evaluation_result_id="result-route",
    )

    client = TestClient(app)
    listed = client.get("/runtime/policy-evidence?evidence_type=decision")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["policy_id"] == policy.id
    assert body[0]["evidence_count"] == 1
    assert body[0]["evidence_items"][0]["evaluation_id"] == "evaluation-route"

    detail = client.get(f"/runtime/policy-evidence/{policy.id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["policy_id"] == policy.id
    assert detail_body["evidence_count"] == 2
    assert detail_body["evaluation_ids"] == ["evaluation-route"]
    assert detail_body["evaluation_result_ids"] == ["result-route"]


def test_policy_evidence_route_returns_not_found_for_missing_policy() -> None:
    response = TestClient(app).get("/runtime/policy-evidence/missing-policy")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Policy evidence not found: missing-policy"
    }


def test_registry_includes_policy_evidence_projection() -> None:
    assert POLICY_EVIDENCE_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
