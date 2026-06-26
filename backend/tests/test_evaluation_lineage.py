from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_lineage import (
    EvaluationEvidenceRecordCreate,
    EvaluationLineageRecordCreate,
)
from app.services.evaluation_lineage_projection_builder_service import (
    EVALUATION_LINEAGE_PROJECTION_TYPE,
    EvaluationLineageProjectionBuilderService,
)
from app.services.evaluation_lineage_service import (
    EvaluationEvidenceAlreadyExistsError,
    EvaluationLineageAlreadyExistsError,
    EvaluationLineageService,
)
from app.services.event_service import EventService
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 22, 14, 0, tzinfo=UTC)


def make_service(tmp_path) -> EvaluationLineageService:
    return EvaluationLineageService(
        events=EventService(TraceService(tmp_path / "evaluation-lineage.db"))
    )


def lineage_request(
    lineage_id: str = "lineage-policy-quality-v1",
) -> EvaluationLineageRecordCreate:
    return EvaluationLineageRecordCreate(
        lineage_id=lineage_id,
        evaluation_id="eval-policy-quality-v1",
        evaluation_name="Policy quality review",
        evaluation_version=1,
        source_type="policy",
        source_id="policy-1",
        source_category="governance",
    )


def evidence_request(
    lineage_id: str = "lineage-policy-quality-v1",
    evidence_id: str = "evidence-policy-decision-1",
) -> EvaluationEvidenceRecordCreate:
    return EvaluationEvidenceRecordCreate(
        evidence_id=evidence_id,
        lineage_id=lineage_id,
        evidence_type="policy_decision",
        evidence_reference="policy-decision-1",
        description="Policy decision that motivated the evaluation.",
    )


def test_lineage_registration_is_event_backed(tmp_path) -> None:
    service = make_service(tmp_path)

    record = service.register_lineage(lineage_request())

    assert record.lineage_id == "lineage-policy-quality-v1"
    assert record.evaluation_id == "eval-policy-quality-v1"
    assert record.evaluation_name == "Policy quality review"
    assert record.evaluation_version == 1
    assert record.source_type == "policy"
    assert record.source_id == "policy-1"
    assert record.source_category == "governance"
    assert service.get_lineage(record.lineage_id) == record
    assert service.list_lineage() == [record]


def test_evidence_registration_links_to_lineage(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_lineage(lineage_request())

    evidence = service.register_evidence(evidence_request())

    assert evidence.evidence_id == "evidence-policy-decision-1"
    assert evidence.lineage_id == "lineage-policy-quality-v1"
    assert evidence.evidence_type == "policy_decision"
    assert evidence.evidence_reference == "policy-decision-1"
    assert service.get_evidence(evidence.evidence_id) == evidence
    assert service.list_evidence() == [evidence]
    assert service.list_evidence(
        lineage_id="lineage-policy-quality-v1"
    ) == [evidence]
    assert service.list_evidence(lineage_id="missing-lineage") == []


def test_duplicate_lineage_and_evidence_are_rejected(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_lineage(lineage_request("lineage-duplicate"))

    try:
        service.register_lineage(lineage_request("lineage-duplicate"))
    except EvaluationLineageAlreadyExistsError as exc:
        assert str(exc) == (
            "Evaluation lineage already registered: lineage-duplicate"
        )
    else:
        raise AssertionError("duplicate lineage was not rejected")

    service.register_evidence(
        evidence_request(
            lineage_id="lineage-duplicate",
            evidence_id="evidence-duplicate",
        )
    )
    try:
        service.register_evidence(
            evidence_request(
                lineage_id="lineage-duplicate",
                evidence_id="evidence-duplicate",
            )
        )
    except EvaluationEvidenceAlreadyExistsError as exc:
        assert str(exc) == (
            "Evaluation evidence already registered: evidence-duplicate"
        )
    else:
        raise AssertionError("duplicate evidence was not rejected")


def test_projection_generation_and_rebuild_are_deterministic(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_lineage(lineage_request("lineage-a"))
    service.register_lineage(
        EvaluationLineageRecordCreate(
            lineage_id="lineage-b",
            evaluation_id="eval-provider-v1",
            evaluation_name="Provider behavior review",
            evaluation_version=1,
            source_type="provider",
            source_id="provider-openai",
            source_category="provider",
        )
    )
    service.register_evidence(
        evidence_request(lineage_id="lineage-a", evidence_id="evidence-a")
    )
    service.register_evidence(
        EvaluationEvidenceRecordCreate(
            evidence_id="evidence-b",
            lineage_id="lineage-b",
            evidence_type="provider_usage",
            evidence_reference="provider-usage-1",
            description="Provider usage record linked to evaluation.",
        )
    )
    builder = EvaluationLineageProjectionBuilderService(
        lineage=service,
        clock=lambda: GENERATED_AT,
    )

    first = builder.build().model_dump(mode="json")
    second = builder.build().model_dump(mode="json")

    assert first == second
    assert first["metadata"]["projection_type"] == (
        EVALUATION_LINEAGE_PROJECTION_TYPE
    )
    assert first["metadata"]["builder_name"] == (
        "EvaluationLineageProjectionBuilderService"
    )
    assert first["metadata"]["reconstruction"] == {
        "projection_type": EVALUATION_LINEAGE_PROJECTION_TYPE,
        "reconstruction_source": "runtime_event_store",
        "rebuildable": True,
        "authoritative_source": "runtime_event_store",
    }
    assert first["total_lineage_records"] == 2
    assert first["total_evidence_records"] == 2
    assert [
        record["lineage_id"]
        for record in first["lineage_records"]
    ] == ["lineage-a", "lineage-b"]
    assert [
        record["evidence_id"]
        for record in first["evidence_records"]
    ] == ["evidence-a", "evidence-b"]


def test_evaluation_lineage_routes_work() -> None:
    client = TestClient(app)

    lineage_response = client.post(
        "/evaluation-lineage",
        json={
            "lineage_id": "lineage-route",
            "evaluation_id": "eval-route",
            "evaluation_name": "Route evaluation",
            "evaluation_version": 1,
            "source_type": "runtime_session",
            "source_id": "session-1",
            "source_category": "runtime",
        },
    )
    assert lineage_response.status_code == 200

    evidence_response = client.post(
        "/evaluation-lineage/evidence",
        json={
            "evidence_id": "evidence-route",
            "lineage_id": "lineage-route",
            "evidence_type": "runtime_session",
            "evidence_reference": "session-1",
            "description": "Runtime session linked to evaluation.",
        },
    )
    assert evidence_response.status_code == 200

    lineage = client.get("/evaluation-lineage")
    evidence = client.get("/evaluation-lineage/evidence")
    filtered_evidence = client.get(
        "/evaluation-lineage/evidence?lineage_id=lineage-route"
    )
    projection = client.get("/evaluation-lineage/projection")
    duplicate = client.post(
        "/evaluation-lineage",
        json={
            "lineage_id": "lineage-route",
            "evaluation_id": "eval-route",
            "evaluation_name": "Route evaluation",
            "evaluation_version": 1,
            "source_type": "runtime_session",
            "source_id": "session-1",
            "source_category": "runtime",
        },
    )

    assert lineage.status_code == 200
    assert evidence.status_code == 200
    assert filtered_evidence.status_code == 200
    assert projection.status_code == 200
    assert duplicate.status_code == 409
    assert lineage.json()[0]["lineage_id"] == "lineage-route"
    assert evidence.json()[0]["evidence_id"] == "evidence-route"
    assert filtered_evidence.json()[0]["lineage_id"] == "lineage-route"
    assert projection.json()["total_lineage_records"] == 1
    assert projection.json()["total_evidence_records"] == 1


def test_projection_registry_and_diagnostics_list_evaluation_lineage() -> None:
    client = TestClient(app)

    runtime_response = client.get("/runtime/projections")
    diagnostics_response = client.get("/runtime/projection-diagnostics")
    contract_response = client.get(
        "/runtime/projections/registry/evaluation_lineage"
    )

    assert runtime_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert contract_response.status_code == 200
    assert EVALUATION_LINEAGE_PROJECTION_TYPE in (
        runtime_response.json()["projection_types"]
    )
    assert EVALUATION_LINEAGE_PROJECTION_TYPE in (
        diagnostics_response.json()["projection_types"]
    )
    assert contract_response.json()["projection_name"] == (
        EVALUATION_LINEAGE_PROJECTION_TYPE
    )
    assert contract_response.json()["route"] == (
        "/evaluation-lineage/projection"
    )
    assert contract_response.json()["capabilities"]["reconstructable"] is True
