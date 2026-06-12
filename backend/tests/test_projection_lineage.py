from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.runtime.projection_registry import (
    ProjectionRegistry,
    ProjectionTypeNotFoundError,
)
from app.services.event_service import EventService, event_service
from app.services.projection_lineage_service import (
    ProjectionLineageGenerationError,
    ProjectionLineageService,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.trace_service import TraceService


class LineageProjectionBuilder:
    projection_type = "lineage_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=4,
        builder_name="LineageProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_session_state",
            authoritative_source="runtime_session",
        ),
    )

    def build(self, source: str):
        raise AssertionError("lineage generation must not build projections")


def make_lineage_service(tmp_path):
    registry = ProjectionRegistry()
    builder = LineageProjectionBuilder()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_lineage.db"))
    sessions = RuntimeSessionService(tmp_path / "runtime_sessions.db")
    session = sessions.create_session("lineage-task")
    service = ProjectionLineageService(
        registry=registry,
        events=events,
        sessions=sessions,
        clock=lambda: datetime(2026, 6, 11, 13, 0, tzinfo=UTC),
    )
    return service, events, sessions, session


def emit_lineage_sources(events: EventService, session_id: str) -> None:
    events.emit_event_sync(
        event_type="planner_completed",
        message="Planner source",
        metadata={
            "session_id": session_id,
            "recommendation_id": "recommendation-1",
        },
    )
    events.emit_event_sync(
        event_type="decision_record_created",
        message="Decision source",
        metadata={
            "session_id": session_id,
            "decision_id": "decision-1",
        },
    )


def test_projection_lineage_is_registry_driven_and_deterministic(
    tmp_path,
) -> None:
    service, events, sessions, session = make_lineage_service(tmp_path)
    emit_lineage_sources(events, session.id)
    before = sessions.get_session(session.id)

    first = service.generate("lineage_projection", session.id)
    second = service.generate("lineage_projection", session.id)

    assert first == second
    assert first.model_dump(mode="json") == {
        "projection_name": "lineage_projection",
        "builder_name": "LineageProjectionBuilder",
        "schema_version": 4,
        "generated_at": session.created_at.isoformat().replace("+00:00", "Z"),
        "reconstruction_info": {
            "projection_type": "lineage_projection",
            "reconstruction_source": "runtime_session_state",
            "rebuildable": True,
            "authoritative_source": "runtime_session",
        },
        "source_types": [
            "decision_record",
            "planner",
            "runtime_event",
            "runtime_session",
            "runtime_session_state",
        ],
        "source_identifiers": {
            "event_ids": [1, 2],
            "session_id": session.id,
            "task_id": session.task_id,
            "decision_ids": ["decision-1"],
            "recommendation_ids": ["recommendation-1"],
        },
        "source_counts": {
            "decision_record": 1,
            "planner": 1,
            "runtime_event": 2,
            "runtime_session": 1,
        },
        "lineage_version": 1,
    }
    after = sessions.get_session(session.id)
    assert (
        after.id,
        after.task_id,
        after.status,
        after.created_at,
        after.completed_at,
    ) == (
        before.id,
        before.task_id,
        before.status,
        before.created_at,
        before.completed_at,
    )

    generated = events.list_persisted_events(
        event_type="projection_lineage_generated"
    )
    assert len(generated) == 2
    assert generated[0].metadata == {
        "projection_name": "lineage_projection",
        "builder_name": "LineageProjectionBuilder",
        "schema_version": 4,
        "source_count": 3,
    }


def test_projection_lineage_unknown_projection_is_clean(tmp_path) -> None:
    service = ProjectionLineageService(registry=ProjectionRegistry())

    with pytest.raises(
        ProjectionTypeNotFoundError,
        match="Projection type not found: missing_projection",
    ):
        service.generate("missing_projection", "session-1")


def test_projection_lineage_failure_emits_diagnostic(tmp_path) -> None:
    service, events, _, _ = make_lineage_service(tmp_path)

    with pytest.raises(
        ProjectionLineageGenerationError,
        match="Runtime session not found",
    ):
        service.generate("lineage_projection", "missing-session")

    failed = events.list_persisted_events(
        event_type="projection_lineage_generation_failed"
    )
    assert len(failed) == 1
    assert failed[0].severity.value == "error"
    assert failed[0].metadata == {
        "projection_name": "lineage_projection",
        "builder_name": "LineageProjectionBuilder",
        "schema_version": 4,
        "source_count": 0,
    }


def test_projection_lineage_endpoint_is_operational() -> None:
    session = runtime_session_service.create_session(
        "projection-lineage-endpoint-task"
    )
    event_service.emit_event_sync(
        event_type="decision_record_created",
        message="Endpoint lineage source",
        metadata={
            "session_id": session.id,
            "decision_id": "endpoint-decision",
        },
    )

    response = TestClient(app).get(
        "/projections/decision_projection/lineage",
        params={"source": session.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_name"] == "decision_projection"
    assert body["builder_name"] == "DecisionProjectionBuilderService"
    assert body["schema_version"] == 1
    assert body["source_identifiers"]["session_id"] == session.id
    assert body["source_identifiers"]["decision_ids"] == [
        "endpoint-decision"
    ]
    assert body["reconstruction_info"]["authoritative_source"] == (
        "runtime_session"
    )


def test_projection_lineage_endpoint_returns_unknown_projection() -> None:
    response = TestClient(app).get(
        "/projections/missing_projection/lineage",
        params={"source": "session-1"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }
