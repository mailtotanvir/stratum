import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.projection_registry import (
    ProjectionRegistry,
    ProjectionTypeAlreadyRegisteredError,
    ProjectionTypeNotFoundError,
    projection_registry,
)
from app.services.decision_projection_builder_service import (
    DECISION_PROJECTION_TYPE,
    decision_projection_builder_service,
)
from app.services.event_service import event_service
from app.services.session_decision_projection_builder_service import (
    SESSION_DECISION_PROJECTION_TYPE,
    session_decision_projection_builder_service,
)


class RecordingProjectionBuilder:
    def __init__(self, projection_type: str) -> None:
        self.projection_type = projection_type
        self.build_calls: list[str] = []

    def build(self, source: str):
        self.build_calls.append(source)
        raise AssertionError("the registry must not build projections")


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
    assert decision_builder.build_calls == []
    assert session_builder.build_calls == []


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
    events_before = event_service.list_persisted_events()

    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert response.json() == {
        "projection_types": [
            DECISION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ]
    }
    assert event_service.list_persisted_events() == events_before


def test_runtime_projection_endpoint_does_not_expose_payloads() -> None:
    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert set(response.json()) == {"projection_types"}
    response_text = response.text
    for excluded_field in (
        "metadata",
        "decision_id",
        "recommendation_id",
        "session_id",
        "projections",
    ):
        assert excluded_field not in response_text
