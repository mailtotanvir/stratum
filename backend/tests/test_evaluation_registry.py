from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_registry import (
    EvaluationDefinitionCreate,
    EvaluationSuiteCreate,
)
from app.services.evaluation_registry_projection_builder_service import (
    EVALUATION_REGISTRY_PROJECTION_TYPE,
    EvaluationRegistryProjectionBuilderService,
)
from app.services.evaluation_registry_service import (
    EvaluationDefinitionAlreadyExistsError,
    EvaluationRegistryService,
    EvaluationSuiteAlreadyExistsError,
)
from app.services.event_service import EventService
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


def make_service(tmp_path) -> EvaluationRegistryService:
    return EvaluationRegistryService(
        events=EventService(TraceService(tmp_path / "evaluation-registry.db"))
    )


def definition_request(
    evaluation_id: str = "eval-policy-quality-v1",
) -> EvaluationDefinitionCreate:
    return EvaluationDefinitionCreate(
        evaluation_id=evaluation_id,
        name="Policy quality review",
        description="Checks policy-linked evaluation quality.",
        category="governance",
        version=1,
        status="active",
    )


def test_definition_registration_is_event_backed(tmp_path) -> None:
    service = make_service(tmp_path)

    definition = service.register_definition(definition_request())

    assert definition.evaluation_id == "eval-policy-quality-v1"
    assert definition.name == "Policy quality review"
    assert definition.category == "governance"
    assert definition.version == 1
    assert definition.status == "active"
    assert service.get_definition(definition.evaluation_id) == definition
    assert service.list_definitions() == [definition]


def test_suite_registration_links_registered_definitions(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_definition(definition_request("eval-policy-quality-v1"))
    service.register_definition(definition_request("eval-policy-safety-v1"))

    suite = service.register_suite(
        EvaluationSuiteCreate(
            suite_id="suite-governance-v1",
            name="Governance suite",
            description="Governance evaluation suite.",
            evaluation_ids=[
                "eval-policy-quality-v1",
                "eval-policy-safety-v1",
            ],
        )
    )

    assert suite.suite_id == "suite-governance-v1"
    assert suite.evaluation_ids == [
        "eval-policy-quality-v1",
        "eval-policy-safety-v1",
    ]
    assert service.get_suite(suite.suite_id) == suite
    assert service.list_suites() == [suite]


def test_duplicate_definitions_and_suites_are_rejected(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_definition(definition_request("eval-duplicate"))

    try:
        service.register_definition(definition_request("eval-duplicate"))
    except EvaluationDefinitionAlreadyExistsError as exc:
        assert str(exc) == (
            "Evaluation definition already registered: eval-duplicate"
        )
    else:
        raise AssertionError("duplicate definition was not rejected")

    service.register_suite(
        EvaluationSuiteCreate(
            suite_id="suite-duplicate",
            name="Duplicate suite",
            description="Suite used for duplicate checks.",
            evaluation_ids=["eval-duplicate"],
        )
    )
    try:
        service.register_suite(
            EvaluationSuiteCreate(
                suite_id="suite-duplicate",
                name="Duplicate suite",
                description="Suite used for duplicate checks.",
                evaluation_ids=["eval-duplicate"],
            )
        )
    except EvaluationSuiteAlreadyExistsError as exc:
        assert str(exc) == (
            "Evaluation suite already registered: suite-duplicate"
        )
    else:
        raise AssertionError("duplicate suite was not rejected")


def test_projection_generation_and_rebuild_are_deterministic(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_definition(definition_request("eval-a"))
    service.register_definition(definition_request("eval-b"))
    service.register_suite(
        EvaluationSuiteCreate(
            suite_id="suite-a",
            name="Suite A",
            description="Suite A description.",
            evaluation_ids=["eval-a", "eval-b"],
        )
    )
    builder = EvaluationRegistryProjectionBuilderService(
        registry=service,
        clock=lambda: GENERATED_AT,
    )

    first = builder.build().model_dump(mode="json")
    second = builder.build().model_dump(mode="json")

    assert first == second
    assert first["metadata"]["projection_type"] == (
        EVALUATION_REGISTRY_PROJECTION_TYPE
    )
    assert first["metadata"]["builder_name"] == (
        "EvaluationRegistryProjectionBuilderService"
    )
    assert first["metadata"]["reconstruction"] == {
        "projection_type": EVALUATION_REGISTRY_PROJECTION_TYPE,
        "reconstruction_source": "runtime_event_store",
        "rebuildable": True,
        "authoritative_source": "runtime_event_store",
    }
    assert first["total_definitions"] == 2
    assert first["total_suites"] == 1
    assert [
        definition["evaluation_id"]
        for definition in first["definitions"]
    ] == ["eval-a", "eval-b"]
    assert first["suites"][0]["evaluation_ids"] == ["eval-a", "eval-b"]


def test_evaluation_registry_routes_work() -> None:
    client = TestClient(app)

    definition_response = client.post(
        "/evaluation-registry/definitions",
        json={
            "evaluation_id": "eval-route",
            "name": "Route evaluation",
            "description": "Registered through the route.",
            "category": "governance",
            "version": 1,
            "status": "active",
        },
    )
    assert definition_response.status_code == 200

    suite_response = client.post(
        "/evaluation-registry/suites",
        json={
            "suite_id": "suite-route",
            "name": "Route suite",
            "description": "Registered through the route.",
            "evaluation_ids": ["eval-route"],
        },
    )
    assert suite_response.status_code == 200

    definitions = client.get("/evaluation-registry/definitions")
    suites = client.get("/evaluation-registry/suites")
    projection = client.get("/evaluation-registry/projection")
    duplicate = client.post(
        "/evaluation-registry/definitions",
        json={
            "evaluation_id": "eval-route",
            "name": "Route evaluation",
            "description": "Registered through the route.",
            "category": "governance",
            "version": 1,
            "status": "active",
        },
    )

    assert definitions.status_code == 200
    assert suites.status_code == 200
    assert projection.status_code == 200
    assert duplicate.status_code == 409
    assert definitions.json()[0]["evaluation_id"] == "eval-route"
    assert suites.json()[0]["suite_id"] == "suite-route"
    assert projection.json()["total_definitions"] == 1
    assert projection.json()["total_suites"] == 1


def test_projection_registry_lists_evaluation_registry() -> None:
    client = TestClient(app)

    runtime_response = client.get("/runtime/projections")
    diagnostics_response = client.get("/runtime/projection-diagnostics")
    contract_response = client.get(
        "/runtime/projections/registry/evaluation_registry"
    )

    assert runtime_response.status_code == 200
    assert EVALUATION_REGISTRY_PROJECTION_TYPE in (
        runtime_response.json()["projection_types"]
    )
    assert contract_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert EVALUATION_REGISTRY_PROJECTION_TYPE in (
        diagnostics_response.json()["projection_types"]
    )
    assert contract_response.json()["projection_name"] == (
        EVALUATION_REGISTRY_PROJECTION_TYPE
    )
    assert contract_response.json()["route"] == (
        "/evaluation-registry/projection"
    )
