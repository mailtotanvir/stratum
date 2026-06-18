import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.projection import ProjectionContract
from app.services.event_service import EventService
from app.services.projection_registry_service import (
    ProjectionContractNotFoundError,
    ProjectionContractValidationError,
    ProjectionRegistrationError,
    ProjectionRegistryService,
    default_projection_contracts,
)
from app.services.trace_service import TraceService


def contract(**overrides) -> ProjectionContract:
    data = {
        "projection_name": "test_projection",
        "projection_version": 1,
        "projection_description": "A deterministic test projection.",
        "projection_owner": "tests",
        "projection_category": "test",
        "supports_replay": True,
        "supports_drift_detection": True,
        "supports_reconstruction": True,
        "supports_analytics": True,
        "supports_explainability": True,
    }
    data.update(overrides)
    return ProjectionContract(**data)


def make_service(tmp_path) -> tuple[ProjectionRegistryService, EventService]:
    events = EventService(TraceService(tmp_path / "projection-registry-v2.db"))
    return ProjectionRegistryService(events=events), events


def test_projection_registration(tmp_path) -> None:
    service, events = make_service(tmp_path)

    entry = service.register(contract())

    assert entry.projection_name == "test_projection"
    assert entry.projection_version == 1
    assert entry.capabilities.replayable is True
    assert entry.capabilities.drift_checkable is True
    assert service.observability_metrics() == {
        "registered_projections_total": 1,
        "projection_contract_validation_failures_total": 0,
        "projection_registry_queries_total": 0,
    }
    assert len(
        events.list_persisted_events(
            event_type="projection_contract_validated"
        )
    ) == 1
    assert len(
        events.list_persisted_events(event_type="projection_registered")
    ) == 1


def test_duplicate_registration_rejection(tmp_path) -> None:
    service, events = make_service(tmp_path)
    service.register(contract())

    with pytest.raises(ProjectionRegistrationError):
        service.register(contract(projection_version=2))

    assert service.list_registry().registered_projections_total == 1
    failed = events.list_persisted_events(
        event_type="projection_registration_failed"
    )
    assert failed[-1].metadata["projection_name"] == "test_projection"


def test_contract_validation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    validated = service.validate_contract(contract())

    assert validated.projection_name == "test_projection"
    assert validated.projection_version == 1


def test_capability_validation(tmp_path) -> None:
    service, events = make_service(tmp_path)

    with pytest.raises(ProjectionContractValidationError):
        service.register(
            contract(
                supports_replay=False,
                supports_drift_detection=True,
            )
        )

    assert service.observability_metrics()[
        "projection_contract_validation_failures_total"
    ] == 1
    invalid = events.list_persisted_events(
        event_type="projection_contract_invalid"
    )
    assert invalid[-1].metadata["error_type"] == "ValueError"


def test_version_validation(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    raw = contract().model_dump()
    raw["projection_version"] = 0

    with pytest.raises(ValidationError):
        service.register(raw)


def test_missing_metadata_is_rejected(tmp_path) -> None:
    service, events = make_service(tmp_path)
    raw = contract().model_dump()
    del raw["projection_owner"]

    with pytest.raises(ValidationError):
        service.register(raw)

    assert service.list_registry().registered_projections_total == 0
    invalid = events.list_persisted_events(
        event_type="projection_contract_invalid"
    )
    assert invalid[-1].metadata["projection_name"] == "test_projection"


def test_registry_list_is_deterministic(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    service.register(contract(projection_name="zeta_projection"))
    service.register(contract(projection_name="alpha_projection"))

    first = service.list_registry()
    second = service.list_registry()

    assert [item.projection_name for item in first.projections] == [
        "alpha_projection",
        "zeta_projection",
    ]
    assert first.projections == second.projections
    assert second.observability_metrics["projection_registry_queries_total"] == 2


def test_unknown_projection_detail_raises_not_found(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    with pytest.raises(ProjectionContractNotFoundError):
        service.get("missing_projection")


def test_default_registry_contracts_cover_v0_6_surfaces() -> None:
    names = [
        item.projection_name
        for item in sorted(
            default_projection_contracts(),
            key=lambda item: item.projection_name,
        )
    ]

    assert names == [
        "artifact_lineage_projection",
        "decision_lineage_projection",
        "decision_projection",
        "evaluation_outcome_rollup",
        "evaluation_summary",
        "evaluation_trend",
        "explainability",
        "governance_audit_projection",
        "operational_analytics",
        "runtime_intelligence",
        "runtime_reconstruction_view",
        "session_decision_projection",
    ]


def test_projection_registry_list_route() -> None:
    response = TestClient(app).get("/runtime/projections/registry")

    assert response.status_code == 200
    body = response.json()
    assert body["registered_projections_total"] == 12
    assert [item["projection_name"] for item in body["projections"]] == [
        "artifact_lineage_projection",
        "decision_lineage_projection",
        "decision_projection",
        "evaluation_outcome_rollup",
        "evaluation_summary",
        "evaluation_trend",
        "explainability",
        "governance_audit_projection",
        "operational_analytics",
        "runtime_intelligence",
        "runtime_reconstruction_view",
        "session_decision_projection",
    ]
    assert body["observability_metrics"]["registered_projections_total"] == 12


def test_projection_registry_detail_route() -> None:
    response = TestClient(app).get(
        "/runtime/projections/registry/decision_lineage_projection"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_name"] == "decision_lineage_projection"
    assert body["capabilities"] == {
        "replayable": True,
        "drift_checkable": True,
        "reconstructable": True,
        "analyzable": True,
        "explainable": True,
    }
    assert body["version_information"] == {
        "projection_name": "decision_lineage_projection",
        "registered_version": 1,
        "version_rule": "one_active_version_per_projection_name",
    }


def test_projection_registry_detail_route_missing_projection() -> None:
    response = TestClient(app).get(
        "/runtime/projections/registry/missing_projection"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection contract not found: missing_projection"
    }
