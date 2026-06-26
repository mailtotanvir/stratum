from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_coverage import (
    CoverageMappingCreate,
    CoverageTargetCreate,
)
from app.models.query_executor import QueryExecutionRequest
from app.services.evaluation_coverage_projection_builder_service import (
    EVALUATION_COVERAGE_PROJECTION_TYPE,
    EvaluationCoverageProjectionBuilderService,
)
from app.services.evaluation_coverage_service import (
    CoverageMappingAlreadyExistsError,
    CoverageTargetAlreadyExistsError,
    EvaluationCoverageService,
)
from app.services.event_service import EventService
from app.services.query_executor_service import query_executor_service
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 22, 16, 0, tzinfo=UTC)


def make_service(tmp_path) -> EvaluationCoverageService:
    return EvaluationCoverageService(
        events=EventService(TraceService(tmp_path / "evaluation-coverage.db"))
    )


def target_request(
    target_id: str = "projection-evaluation-summary",
) -> CoverageTargetCreate:
    return CoverageTargetCreate(
        target_id=target_id,
        target_name="Evaluation Summary Projection",
        target_type="projection",
        target_category="evaluations",
        description="Runtime evaluation summary projection.",
    )


def mapping_request(
    target_id: str = "projection-evaluation-summary",
    mapping_id: str = "coverage-eval-summary",
) -> CoverageMappingCreate:
    return CoverageMappingCreate(
        mapping_id=mapping_id,
        target_id=target_id,
        evaluation_id="eval-summary-contract-v1",
        evaluation_name="Evaluation summary contract check",
        evaluation_version=1,
    )


def test_target_registration_is_event_backed(tmp_path) -> None:
    service = make_service(tmp_path)

    target = service.register_target(target_request())

    assert target.target_id == "projection-evaluation-summary"
    assert target.target_name == "Evaluation Summary Projection"
    assert target.target_type == "projection"
    assert target.target_category == "evaluations"
    assert service.get_target(target.target_id) == target
    assert service.list_targets() == [target]


def test_mapping_registration_links_to_registered_target(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_target(target_request())

    mapping = service.register_mapping(mapping_request())

    assert mapping.mapping_id == "coverage-eval-summary"
    assert mapping.target_id == "projection-evaluation-summary"
    assert mapping.evaluation_id == "eval-summary-contract-v1"
    assert mapping.evaluation_name == "Evaluation summary contract check"
    assert service.get_mapping(mapping.mapping_id) == mapping
    assert service.list_mappings() == [mapping]
    assert service.list_mappings(
        target_id="projection-evaluation-summary"
    ) == [mapping]
    assert service.list_mappings(target_id="missing-target") == []


def test_duplicate_targets_and_mappings_are_rejected(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_target(target_request("target-duplicate"))

    try:
        service.register_target(target_request("target-duplicate"))
    except CoverageTargetAlreadyExistsError as exc:
        assert str(exc) == (
            "Coverage target already registered: target-duplicate"
        )
    else:
        raise AssertionError("duplicate target was not rejected")

    service.register_mapping(
        mapping_request(
            target_id="target-duplicate",
            mapping_id="mapping-duplicate",
        )
    )
    try:
        service.register_mapping(
            mapping_request(
                target_id="target-duplicate",
                mapping_id="mapping-duplicate",
            )
        )
    except CoverageMappingAlreadyExistsError as exc:
        assert str(exc) == (
            "Coverage mapping already registered: mapping-duplicate"
        )
    else:
        raise AssertionError("duplicate mapping was not rejected")


def test_projection_calculates_coverage_deterministically(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_target(target_request("projection-evaluation-summary"))
    service.register_target(
        CoverageTargetCreate(
            target_id="policy-governance",
            target_name="Governance Policy",
            target_type="policy",
            target_category="governance",
            description="Governance policy target.",
        )
    )
    service.register_target(
        CoverageTargetCreate(
            target_id="runtime-provider",
            target_name="Provider Runtime",
            target_type="runtime_component",
            target_category="provider",
            description="Provider runtime target.",
        )
    )
    service.register_mapping(
        mapping_request(target_id="projection-evaluation-summary")
    )
    service.register_mapping(
        CoverageMappingCreate(
            mapping_id="coverage-policy-governance",
            target_id="policy-governance",
            evaluation_id="eval-policy-v1",
            evaluation_name="Policy coverage check",
            evaluation_version=1,
        )
    )
    builder = EvaluationCoverageProjectionBuilderService(
        coverage=service,
        clock=lambda: GENERATED_AT,
    )

    first = builder.build().model_dump(mode="json")
    second = builder.build().model_dump(mode="json")

    assert first == second
    assert first["metadata"]["projection_type"] == (
        EVALUATION_COVERAGE_PROJECTION_TYPE
    )
    assert first["metadata"]["builder_name"] == (
        "EvaluationCoverageProjectionBuilderService"
    )
    assert first["metadata"]["reconstruction"] == {
        "projection_type": EVALUATION_COVERAGE_PROJECTION_TYPE,
        "reconstruction_source": "runtime_event_store",
        "rebuildable": True,
        "authoritative_source": "runtime_event_store",
    }
    assert first["total_targets"] == 3
    assert first["coverage_percentage"] == 2 / 3 * 100
    assert [
        target["target_id"]
        for target in first["covered_targets"]
    ] == [
        "projection-evaluation-summary",
        "policy-governance",
    ]
    assert [
        target["target_id"]
        for target in first["uncovered_targets"]
    ] == ["runtime-provider"]


def test_empty_projection_has_zero_coverage(tmp_path) -> None:
    builder = EvaluationCoverageProjectionBuilderService(
        coverage=make_service(tmp_path),
        clock=lambda: GENERATED_AT,
    )

    projection = builder.build()

    assert projection.total_targets == 0
    assert projection.covered_targets == []
    assert projection.uncovered_targets == []
    assert projection.coverage_percentage == 0.0


def test_evaluation_coverage_routes_work() -> None:
    client = TestClient(app)

    target_response = client.post(
        "/evaluation-coverage/targets",
        json={
            "target_id": "route-target",
            "target_name": "Route Target",
            "target_type": "query",
            "target_category": "evaluations",
            "description": "Coverage target registered through route.",
        },
    )
    assert target_response.status_code == 200

    mapping_response = client.post(
        "/evaluation-coverage/mappings",
        json={
            "mapping_id": "route-mapping",
            "target_id": "route-target",
            "evaluation_id": "eval-route",
            "evaluation_name": "Route coverage evaluation",
            "evaluation_version": 1,
        },
    )
    assert mapping_response.status_code == 200

    targets = client.get("/evaluation-coverage/targets")
    mappings = client.get("/evaluation-coverage/mappings")
    filtered_mappings = client.get(
        "/evaluation-coverage/mappings?target_id=route-target"
    )
    projection = client.get("/evaluation-coverage/projection")
    duplicate = client.post(
        "/evaluation-coverage/targets",
        json={
            "target_id": "route-target",
            "target_name": "Route Target",
            "target_type": "query",
            "target_category": "evaluations",
            "description": "Coverage target registered through route.",
        },
    )

    assert targets.status_code == 200
    assert mappings.status_code == 200
    assert filtered_mappings.status_code == 200
    assert projection.status_code == 200
    assert duplicate.status_code == 409
    assert targets.json()[0]["target_id"] == "route-target"
    assert mappings.json()[0]["mapping_id"] == "route-mapping"
    assert filtered_mappings.json()[0]["target_id"] == "route-target"
    assert projection.json()["total_targets"] == 1
    assert projection.json()["coverage_percentage"] == 100.0


def test_projection_registry_diagnostics_and_query_executor_visibility() -> None:
    client = TestClient(app)

    runtime_response = client.get("/runtime/projections")
    diagnostics_response = client.get("/runtime/projection-diagnostics")
    contract_response = client.get(
        "/runtime/projections/registry/evaluation_coverage"
    )
    query_response = client.post(
        "/runtime/query-execute",
        json={"query_id": "evaluation_coverage"},
    )
    direct_query = query_executor_service.execute(
        QueryExecutionRequest(query_id="runtime.evaluation_coverage")
    )

    assert runtime_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert contract_response.status_code == 200
    assert query_response.status_code == 200
    assert EVALUATION_COVERAGE_PROJECTION_TYPE in (
        runtime_response.json()["projection_types"]
    )
    assert EVALUATION_COVERAGE_PROJECTION_TYPE in (
        diagnostics_response.json()["projection_types"]
    )
    assert contract_response.json()["projection_name"] == (
        EVALUATION_COVERAGE_PROJECTION_TYPE
    )
    assert contract_response.json()["route"] == (
        "/evaluation-coverage/projection"
    )
    assert contract_response.json()["capabilities"]["reconstructable"] is True
    assert query_response.json()["projection_type"] == (
        EVALUATION_COVERAGE_PROJECTION_TYPE
    )
    assert query_response.json()["result"]["total_targets"] == 0
    assert direct_query.projection_type == EVALUATION_COVERAGE_PROJECTION_TYPE
