from fastapi.testclient import TestClient

from app.main import app
from app.services.policy_diagnostics_service import policy_diagnostics_service
from app.services.policy_service import PolicyService


def make_fixture(tmp_path):
    return PolicyService(tmp_path / "policies.db")


def test_diagnostics_returns_policy_counts(tmp_path) -> None:
    policies = make_fixture(tmp_path)
    active = policies.create_policy(
        name="Active policy",
        description="Has all policy activity.",
        policy_type="runtime",
        status="active",
    )
    draft = policies.create_policy(
        name="Draft policy",
        description="Has no activity yet.",
        policy_type="runtime",
        status="draft",
    )
    active_version = policies.add_policy_version(
        policy_id=active.id,
        version=1,
        rule_payload={"mode": "observe"},
    )
    policies.add_policy_version(
        policy_id=draft.id,
        version=1,
        rule_payload={"mode": "observe"},
    )
    policies.record_policy_decision(
        policy_id=active.id,
        policy_version_id=active_version.id,
        target_type="artifact",
        target_id="artifact-1",
        decision="allowed",
        reason="Observed.",
        evaluation_id="evaluation-1",
    )
    policies.record_policy_violation(
        policy_id=active.id,
        policy_version_id=active_version.id,
        target_type="artifact",
        target_id="artifact-1",
        severity="warning",
        message="Observed.",
        evaluation_result_id="result-1",
    )

    service = type(policy_diagnostics_service)(policies=policies)
    diagnostics = service.generate()

    assert diagnostics.policy_count == 2
    assert diagnostics.policy_version_count == 2
    assert diagnostics.policy_decision_count == 1
    assert diagnostics.policy_violation_count == 1
    assert diagnostics.policy_decisions_with_evaluation_count == 1
    assert diagnostics.policy_violations_with_evaluation_count == 1


def test_diagnostics_counts_evaluation_linked_policy_activity(tmp_path) -> None:
    policies = make_fixture(tmp_path)
    policy = policies.create_policy(
        name="Evaluation-linked policy",
        description="Has evaluation attribution.",
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
        reason="No evaluation link.",
    )
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-1",
        decision="needs_review",
        reason="Evaluation link.",
        evaluation_id="evaluation-1",
    )
    policies.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id="result-1",
        decision="allowed",
        reason="Result link.",
        evaluation_result_id="result-1",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-1",
        severity="warning",
        message="No evaluation link.",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-1",
        severity="warning",
        message="Evaluation link.",
        evaluation_id="evaluation-1",
    )
    policies.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id="result-1",
        severity="critical",
        message="Result link.",
        evaluation_result_id="result-1",
    )

    service = type(policy_diagnostics_service)(policies=policies)
    diagnostics = service.generate()

    assert diagnostics.policy_decisions_with_evaluation_count == 2
    assert diagnostics.policy_violations_with_evaluation_count == 2


def test_diagnostics_identifies_policies_without_versions(tmp_path) -> None:
    policies = make_fixture(tmp_path)
    with_version = policies.create_policy(
        name="Versioned policy",
        description="Has a version.",
        policy_type="runtime",
        status="active",
    )
    policies.add_policy_version(with_version.id, 1, {"mode": "observe"})
    policies.create_policy(
        name="Unversioned policy",
        description="Has no versions.",
        policy_type="runtime",
        status="draft",
    )

    service = type(policy_diagnostics_service)(policies=policies)

    assert service.generate().policies_without_versions_count == 1


def test_diagnostics_identifies_policies_without_decisions(tmp_path) -> None:
    policies = make_fixture(tmp_path)
    with_decision = policies.create_policy(
        name="Policy with decision",
        description="Has a recorded decision.",
        policy_type="runtime",
        status="active",
    )
    version = policies.add_policy_version(
        with_decision.id,
        1,
        {"mode": "observe"},
    )
    policies.record_policy_decision(
        policy_id=with_decision.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-1",
        decision="allowed",
        reason="Observed.",
    )
    policies.create_policy(
        name="Policy without decision",
        description="No decisions recorded.",
        policy_type="runtime",
        status="draft",
    )

    service = type(policy_diagnostics_service)(policies=policies)

    assert service.generate().policies_without_decisions_count == 1


def test_diagnostics_identifies_policies_without_violations(tmp_path) -> None:
    policies = make_fixture(tmp_path)
    with_violation = policies.create_policy(
        name="Policy with violation",
        description="Has a recorded violation.",
        policy_type="runtime",
        status="active",
    )
    version = policies.add_policy_version(
        with_violation.id,
        1,
        {"mode": "observe"},
    )
    policies.record_policy_violation(
        policy_id=with_violation.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-1",
        severity="warning",
        message="Observed.",
    )
    policies.create_policy(
        name="Policy without violation",
        description="No violations recorded.",
        policy_type="runtime",
        status="draft",
    )

    service = type(policy_diagnostics_service)(policies=policies)

    assert service.generate().policies_without_violations_count == 1


def test_diagnostics_lists_registered_policy_summary_projection(
    tmp_path,
) -> None:
    policies = make_fixture(tmp_path)
    service = type(policy_diagnostics_service)(policies=policies)

    diagnostics = service.generate()

    assert diagnostics.registered_projection_types == [
        "policy_evaluation_overview",
        "policy_evidence",
        "policy_summary",
    ]
    assert len(diagnostics.projections) == 3
    projection_by_type = {
        projection.projection_type: projection
        for projection in diagnostics.projections
    }
    evidence = projection_by_type["policy_evidence"]
    assert evidence.registered is True
    assert evidence.rebuildable is True
    assert evidence.persisted is False
    assert evidence.source == (
        "policies/policy_decisions/policy_violations/evaluations"
    )
    assert evidence.route == "/runtime/policy-evidence"
    overview = projection_by_type["policy_evaluation_overview"]
    assert overview.registered is True
    assert overview.rebuildable is True
    assert overview.persisted is False
    assert overview.source == (
        "policies/policy_decisions/policy_violations/"
        "runtime_evaluation_records"
    )
    assert overview.route == "/runtime/policy-evaluation-overview"
    summary = projection_by_type["policy_summary"]
    assert summary.registered is True
    assert summary.rebuildable is True
    assert summary.persisted is False
    assert summary.source == (
        "policies/policy_versions/policy_decisions/policy_violations"
    )
    assert summary.route == "/runtime/policy-projections"


def test_policy_diagnostics_route_works() -> None:
    response = TestClient(app).get("/runtime/policy-diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert {
        "policy_count",
        "policy_version_count",
        "policy_decision_count",
        "policy_violation_count",
        "policy_decisions_with_evaluation_count",
        "policy_violations_with_evaluation_count",
        "policies_without_versions_count",
        "policies_without_decisions_count",
        "policies_without_violations_count",
        "registered_projection_types",
        "projections",
        "generated_at",
    } == set(body)
