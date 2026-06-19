from fastapi.testclient import TestClient

from app.main import app
from app.services.event_service import event_service
from app.services.policy_service import PolicyService


def test_policy_creation_retrieval_listing_and_event(tmp_path) -> None:
    service = PolicyService(tmp_path / "policies.db")

    policy = service.create_policy(
        name="Artifact review policy",
        description="Records expected review behavior.",
        policy_type="evaluation",
        status="active",
    )

    assert service.get_policy(policy.id).name == "Artifact review policy"
    assert [record.id for record in service.list_policies()] == [policy.id]

    events = event_service.list_persisted_events(event_type="policy_created")
    assert len(events) == 1
    assert events[0].metadata["policy_id"] == policy.id
    assert events[0].metadata["policy_type"] == "evaluation"
    assert events[0].metadata["status"] == "active"


def test_policy_version_creation_is_recorded_and_retrievable(tmp_path) -> None:
    service = PolicyService(tmp_path / "policies.db")
    policy = service.create_policy(
        name="Runtime observation policy",
        description="Records observation rules.",
        policy_type="runtime",
        status="draft",
    )

    version = service.add_policy_version(
        policy_id=policy.id,
        version=1,
        rule_payload={"checks": [{"field": "score", "minimum": 0.8}]},
    )

    assert version.policy_id == policy.id
    assert service.rule_payload_for(version) == {
        "checks": [{"field": "score", "minimum": 0.8}]
    }
    assert [record.id for record in service.list_policy_versions(policy.id)] == [
        version.id
    ]

    events = event_service.list_persisted_events(
        event_type="policy_version_added"
    )
    assert len(events) == 1
    assert events[0].metadata["policy_id"] == policy.id
    assert events[0].metadata["policy_version_id"] == version.id
    assert events[0].metadata["version"] == 1


def test_policy_decision_recording_records_outcome_only(tmp_path) -> None:
    service = PolicyService(tmp_path / "policies.db")
    policy = service.create_policy(
        name="Decision policy",
        description="Records decisions.",
        policy_type="decision",
        status="active",
    )
    version = service.add_policy_version(policy.id, 1, {"mode": "observe"})

    decision = service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="artifact",
        target_id="artifact-123",
        decision="allowed",
        reason="All observation criteria met.",
        metadata={"source": "test"},
    )

    assert decision.policy_id == policy.id
    assert decision.policy_version_id == version.id
    assert decision.evaluation_id is None
    assert decision.evaluation_result_id is None
    assert service.decision_metadata_for(decision) == {"source": "test"}
    assert [record.id for record in service.list_policy_decisions(policy.id)] == [
        decision.id
    ]

    events = event_service.list_persisted_events(
        event_type="policy_decision_recorded"
    )
    assert len(events) == 1
    assert events[0].metadata["policy_decision_id"] == decision.id
    assert events[0].metadata["decision"] == "allowed"
    assert "evaluation_id" not in events[0].metadata
    assert "evaluation_result_id" not in events[0].metadata


def test_policy_decision_can_reference_evaluation_evidence(tmp_path) -> None:
    service = PolicyService(tmp_path / "policies.db")
    policy = service.create_policy(
        name="Evaluation-linked decision policy",
        description="Records evaluation attribution.",
        policy_type="evaluation",
        status="active",
    )
    version = service.add_policy_version(policy.id, 1, {"mode": "observe"})

    by_evaluation = service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-123",
        decision="needs_review",
        reason="Based on evaluation.",
        evaluation_id="evaluation-123",
    )
    by_result = service.record_policy_decision(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id="result-123",
        decision="allowed",
        reason="Based on evaluation result.",
        evaluation_result_id="result-123",
    )

    assert by_evaluation.evaluation_id == "evaluation-123"
    assert by_evaluation.evaluation_result_id is None
    assert by_result.evaluation_id is None
    assert by_result.evaluation_result_id == "result-123"
    events = event_service.list_persisted_events(
        event_type="policy_decision_recorded"
    )
    assert events[-2].metadata["evaluation_id"] == "evaluation-123"
    assert "evaluation_result_id" not in events[-2].metadata
    assert events[-1].metadata["evaluation_result_id"] == "result-123"
    assert "evaluation_id" not in events[-1].metadata


def test_policy_violation_recording_records_observation_only(tmp_path) -> None:
    service = PolicyService(tmp_path / "policies.db")
    policy = service.create_policy(
        name="Violation policy",
        description="Records violations.",
        policy_type="quality",
        status="active",
    )
    version = service.add_policy_version(policy.id, 1, {"mode": "observe"})

    violation = service.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-123",
        severity="warning",
        message="Score below target.",
        metadata={"score": 0.4},
    )

    assert violation.policy_id == policy.id
    assert violation.policy_version_id == version.id
    assert violation.evaluation_id is None
    assert violation.evaluation_result_id is None
    assert service.violation_metadata_for(violation) == {"score": 0.4}
    assert [record.id for record in service.list_policy_violations(policy.id)] == [
        violation.id
    ]

    events = event_service.list_persisted_events(
        event_type="policy_violation_recorded"
    )
    assert len(events) == 1
    assert events[0].metadata["policy_violation_id"] == violation.id
    assert events[0].metadata["severity"] == "warning"
    assert "evaluation_id" not in events[0].metadata
    assert "evaluation_result_id" not in events[0].metadata


def test_policy_violation_can_reference_evaluation_evidence(tmp_path) -> None:
    service = PolicyService(tmp_path / "policies.db")
    policy = service.create_policy(
        name="Evaluation-linked violation policy",
        description="Records evaluation attribution.",
        policy_type="evaluation",
        status="active",
    )
    version = service.add_policy_version(policy.id, 1, {"mode": "observe"})

    by_evaluation = service.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation",
        target_id="evaluation-456",
        severity="warning",
        message="Based on evaluation.",
        evaluation_id="evaluation-456",
    )
    by_result = service.record_policy_violation(
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type="evaluation_result",
        target_id="result-456",
        severity="critical",
        message="Based on evaluation result.",
        evaluation_result_id="result-456",
    )

    assert by_evaluation.evaluation_id == "evaluation-456"
    assert by_evaluation.evaluation_result_id is None
    assert by_result.evaluation_id is None
    assert by_result.evaluation_result_id == "result-456"
    events = event_service.list_persisted_events(
        event_type="policy_violation_recorded"
    )
    assert events[-2].metadata["evaluation_id"] == "evaluation-456"
    assert "evaluation_result_id" not in events[-2].metadata
    assert events[-1].metadata["evaluation_result_id"] == "result-456"
    assert "evaluation_id" not in events[-1].metadata


def test_policy_routes_are_registered_and_return_policy_detail() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/policies",
        json={
            "name": "Route policy",
            "description": "Created through API.",
            "policy_type": "runtime",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    policy = create_response.json()

    version_response = client.post(
        f"/policies/{policy['id']}/versions",
        json={"version": 1, "rule_payload": {"mode": "observe"}},
    )
    assert version_response.status_code == 200
    version = version_response.json()

    decision_response = client.post(
        f"/policies/{policy['id']}/decisions",
        json={
            "policy_version_id": version["id"],
            "target_type": "artifact",
            "target_id": "artifact-route",
            "decision": "allowed",
            "reason": "Observation recorded.",
            "evaluation_id": "evaluation-route",
            "evaluation_result_id": "result-route",
            "metadata": {"route": True},
        },
    )
    assert decision_response.status_code == 200

    violation_response = client.post(
        f"/policies/{policy['id']}/violations",
        json={
            "policy_version_id": version["id"],
            "target_type": "artifact",
            "target_id": "artifact-route",
            "severity": "warning",
            "message": "Observation recorded.",
            "evaluation_id": "evaluation-route",
            "evaluation_result_id": "result-route",
            "metadata": {"route": True},
        },
    )
    assert violation_response.status_code == 200

    list_response = client.get("/policies")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [policy["id"]]

    detail_response = client.get(f"/policies/{policy['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == policy["id"]
    assert detail["versions"][0]["id"] == version["id"]
    assert detail["versions"][0]["rule_payload"] == {"mode": "observe"}
    assert detail["decisions"][0]["decision"] == "allowed"
    assert detail["decisions"][0]["evaluation_id"] == "evaluation-route"
    assert detail["decisions"][0]["evaluation_result_id"] == "result-route"
    assert detail["decisions"][0]["metadata"] == {"route": True}
    assert detail["violations"][0]["severity"] == "warning"
    assert detail["violations"][0]["evaluation_id"] == "evaluation-route"
    assert detail["violations"][0]["evaluation_result_id"] == "result-route"
    assert detail["violations"][0]["metadata"] == {"route": True}


def test_policy_route_returns_not_found_for_missing_policy() -> None:
    response = TestClient(app).get("/policies/missing-policy")

    assert response.status_code == 404
