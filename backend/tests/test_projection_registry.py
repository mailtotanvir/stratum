import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.runtime.projection_registry import (
    ProjectionContractError,
    ProjectionRegistry,
    ProjectionTypeAlreadyRegisteredError,
    ProjectionTypeNotFoundError,
    projection_registry,
)
from app.services.decision_projection_builder_service import (
    DECISION_PROJECTION_SCHEMA_VERSION,
    DECISION_PROJECTION_TYPE,
    decision_projection_builder_service,
)
from app.services.event_service import event_service
from app.services.session_decision_projection_builder_service import (
    SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
    SESSION_DECISION_PROJECTION_TYPE,
    session_decision_projection_builder_service,
)

MISSING = object()


class RecordingProjectionBuilder:
    def __init__(
        self,
        projection_type: str,
        schema_version: int = 1,
    ) -> None:
        self.projection_type = projection_type
        self.schema_info = ProjectionSchemaInfo(
            projection_type=projection_type,
            schema_version=schema_version,
            builder_name=type(self).__name__,
            reconstruction=ProjectionReconstructionInfo(
                projection_type=projection_type,
                reconstruction_source="test_state",
                authoritative_source="test_source",
            ),
        )
        self.build_calls: list[str] = []

    def build(self, source: str):
        self.build_calls.append(source)
        raise AssertionError("the registry must not build projections")


class RawContractProjectionBuilder:
    projection_type = "raw_projection"

    def __init__(self, schema_info: dict) -> None:
        self.schema_info = schema_info

    def build(self, source: str):
        raise AssertionError("contract validation must not build projections")


def valid_raw_contract() -> dict:
    return {
        "projection_type": "raw_projection",
        "schema_version": 1,
        "builder_name": "RawContractProjectionBuilder",
        "reconstruction": {
            "projection_type": "raw_projection",
            "reconstruction_source": "runtime_session_state",
            "rebuildable": True,
            "authoritative_source": "runtime_session",
        },
    }


def test_projection_builders_register_and_lookup_by_unique_type() -> None:
    registry = ProjectionRegistry()
    decision_builder = RecordingProjectionBuilder("decision_projection")
    session_builder = RecordingProjectionBuilder(
        "session_decision_projection"
    )

    registry.register(decision_builder)
    registry.register(session_builder)

    assert registry.list_projection_types() == [
        "decision_projection",
        "session_decision_projection",
    ]
    assert registry.get("decision_projection") is decision_builder
    assert registry.get("session_decision_projection") is session_builder
    assert registry.list_schemas() == [
        decision_builder.schema_info,
        session_builder.schema_info,
    ]
    assert decision_builder.build_calls == []
    assert session_builder.build_calls == []


def test_valid_raw_projection_contract_registers_successfully() -> None:
    registry = ProjectionRegistry()
    builder = RawContractProjectionBuilder(valid_raw_contract())

    registry.register(builder)

    assert registry.get("raw_projection") is builder
    assert registry.get_schema("raw_projection").model_dump() == (
        valid_raw_contract()
    )


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    [
        pytest.param(
            ("projection_type",),
            "",
            id="missing-projection-type",
        ),
        pytest.param(
            ("schema_version",),
            MISSING,
            id="missing-schema-version",
        ),
        pytest.param(
            ("builder_name",),
            "",
            id="missing-builder-name",
        ),
        pytest.param(
            ("reconstruction", "reconstruction_source"),
            "",
            id="missing-reconstruction-source",
        ),
        pytest.param(
            ("reconstruction", "authoritative_source"),
            "",
            id="missing-authoritative-source",
        ),
        pytest.param(
            ("reconstruction", "rebuildable"),
            False,
            id="not-rebuildable",
        ),
    ],
)
def test_invalid_projection_contract_is_rejected(
    field_path: tuple[str, ...],
    invalid_value,
) -> None:
    contract = valid_raw_contract()
    target = contract
    for field_name in field_path[:-1]:
        target = target[field_name]
    if invalid_value is MISSING:
        del target[field_path[-1]]
    else:
        target[field_path[-1]] = invalid_value
    registry = ProjectionRegistry()

    with pytest.raises(ProjectionContractError):
        registry.register(RawContractProjectionBuilder(contract))

    assert registry.list_projection_types() == []


def test_projection_types_must_be_unique() -> None:
    registry = ProjectionRegistry()
    registry.register(RecordingProjectionBuilder("decision_projection"))

    with pytest.raises(
        ProjectionTypeAlreadyRegisteredError,
        match="Projection type already registered: decision_projection",
    ):
        registry.register(RecordingProjectionBuilder("decision_projection"))


def test_unknown_projection_lookup_raises_predictable_error() -> None:
    registry = ProjectionRegistry()

    with pytest.raises(
        ProjectionTypeNotFoundError,
        match="Projection type not found: missing_projection",
    ):
        registry.get("missing_projection")


def test_runtime_registry_contains_existing_builders() -> None:
    assert projection_registry.list_projection_types() == [
        DECISION_PROJECTION_TYPE,
        SESSION_DECISION_PROJECTION_TYPE,
    ]
    assert (
        projection_registry.get(DECISION_PROJECTION_TYPE)
        is decision_projection_builder_service
    )
    assert (
        projection_registry.get(SESSION_DECISION_PROJECTION_TYPE)
        is session_decision_projection_builder_service
    )
    assert not hasattr(projection_registry, "build")


def test_runtime_registry_exposes_stable_schema_contracts() -> None:
    schemas = projection_registry.list_schemas()

    assert [schema.model_dump() for schema in schemas] == [
        {
            "projection_type": DECISION_PROJECTION_TYPE,
            "schema_version": DECISION_PROJECTION_SCHEMA_VERSION,
            "builder_name": "DecisionProjectionBuilderService",
            "reconstruction": {
                "projection_type": DECISION_PROJECTION_TYPE,
                "reconstruction_source": "runtime_session_state",
                "rebuildable": True,
                "authoritative_source": "runtime_session",
            },
        },
        {
            "projection_type": SESSION_DECISION_PROJECTION_TYPE,
            "schema_version": SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
            "builder_name": "SessionDecisionProjectionBuilderService",
            "reconstruction": {
                "projection_type": SESSION_DECISION_PROJECTION_TYPE,
                "reconstruction_source": "decision_projection",
                "rebuildable": True,
                "authoritative_source": "runtime_session",
            },
        },
    ]
    assert projection_registry.get_schema(
        DECISION_PROJECTION_TYPE
    ) is not decision_projection_builder_service.schema_info


def test_runtime_projection_endpoint_lists_types_without_building(
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("projection diagnostics must not build projections")

    monkeypatch.setattr(decision_projection_builder_service, "build", fail)
    monkeypatch.setattr(
        session_decision_projection_builder_service,
        "build",
        fail,
    )

    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert response.json() == {
        "projection_types": [
            DECISION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ],
        "schemas": [
            {
                "projection_type": DECISION_PROJECTION_TYPE,
                "schema_version": DECISION_PROJECTION_SCHEMA_VERSION,
                "builder_name": "DecisionProjectionBuilderService",
                "reconstruction": {
                    "projection_type": DECISION_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_session_state",
                    "rebuildable": True,
                    "authoritative_source": "runtime_session",
                },
            },
            {
                "projection_type": SESSION_DECISION_PROJECTION_TYPE,
                "schema_version": SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
                "builder_name": "SessionDecisionProjectionBuilderService",
                "reconstruction": {
                    "projection_type": SESSION_DECISION_PROJECTION_TYPE,
                    "reconstruction_source": "decision_projection",
                    "rebuildable": True,
                    "authoritative_source": "runtime_session",
                },
            },
        ],
    }
    events = event_service.list_persisted_events(
        event_type="projection_registry_inspected"
    )
    assert len(events) == 1
    assert events[0].metadata == {
        "projection_type_count": 2,
        "projection_types": [
            DECISION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ],
        "source": "projection_registry",
    }


def test_runtime_projection_endpoint_does_not_expose_payloads() -> None:
    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert set(response.json()) == {"projection_types", "schemas"}
    response_text = response.text
    for excluded_field in (
        "metadata",
        "decision_id",
        "recommendation_id",
        "session_id",
        "projections",
    ):
        assert excluded_field not in response_text


@pytest.mark.parametrize(
    (
        "projection_type",
        "schema_version",
        "builder_name",
        "reconstruction_source",
    ),
    [
        (
            DECISION_PROJECTION_TYPE,
            DECISION_PROJECTION_SCHEMA_VERSION,
            "DecisionProjectionBuilderService",
            "runtime_session_state",
        ),
        (
            SESSION_DECISION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
            "SessionDecisionProjectionBuilderService",
            "decision_projection",
        ),
    ],
)
def test_runtime_projection_type_detail_returns_discovery_metadata(
    projection_type: str,
    schema_version: int,
    builder_name: str,
    reconstruction_source: str,
) -> None:
    response = TestClient(app).get(
        f"/runtime/projections/{projection_type}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "projection_type": projection_type,
        "schema_version": schema_version,
        "registered": True,
        "builder_name": builder_name,
        "reconstruction": {
            "projection_type": projection_type,
            "reconstruction_source": reconstruction_source,
            "rebuildable": True,
            "authoritative_source": "runtime_session",
        },
        "source": "projection_registry",
    }


def test_runtime_projection_type_detail_returns_standard_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/projections/missing_projection"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }


def test_runtime_projection_type_detail_does_not_build_or_expose_payloads(
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("projection discovery must not build projections")

    monkeypatch.setattr(decision_projection_builder_service, "build", fail)

    response = TestClient(app).get(
        f"/runtime/projections/{DECISION_PROJECTION_TYPE}"
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "projection_type",
        "schema_version",
        "registered",
        "builder_name",
        "reconstruction",
        "source",
    }
    response_text = response.text
    for excluded_field in (
        "metadata",
        "decision_id",
        "recommendation_id",
        "session_id",
        "planning_context",
        "cognitive_state",
        "projections",
    ):
        assert excluded_field not in response_text


def test_runtime_projection_list_behavior_remains_unchanged() -> None:
    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert response.json() == {
        "projection_types": [
            DECISION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ],
        "schemas": [
            decision_projection_builder_service.schema_info.model_dump(),
            session_decision_projection_builder_service.schema_info.model_dump(),
        ],
    }
