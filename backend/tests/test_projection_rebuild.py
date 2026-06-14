from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    Projection,
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.runtime.projection_registry import ProjectionRegistry
from app.services.decision_projection_builder_service import (
    decision_projection_builder_service,
)
from app.services.event_service import EventService, event_service
from app.services.projection_rebuild_service import (
    ProjectionRebuildService,
    ProjectionRebuildValidationError,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


class ExampleProjection(Projection):
    value: str


class ExampleProjectionBuilder:
    projection_type = "example_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=1,
        builder_name="ExampleProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="test_runtime_state",
            authoritative_source="test_event_store",
        ),
    )

    def build(self, source: str) -> ExampleProjection:
        return ExampleProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
                source="example_projection_builder",
            ),
            value=source,
        )


class InvalidExampleProjectionBuilder(ExampleProjectionBuilder):
    def build(self, source: str) -> ExampleProjection:
        return ExampleProjection(
            metadata=ProjectionMetadata(
                projection_type=self.projection_type,
                schema_version=2,
                builder_name="UnexpectedBuilder",
                reconstruction=self.schema_info.reconstruction,
                built_at=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
                source="invalid_example_projection_builder",
            ),
            value=source,
        )


def make_rebuild_service(
    tmp_path,
    builder: ExampleProjectionBuilder,
) -> tuple[ProjectionRebuildService, EventService]:
    registry = ProjectionRegistry()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_rebuild.db"))
    return ProjectionRebuildService(registry, events), events


def test_rebuild_known_projection_returns_data_and_reconstruction_metadata(
    tmp_path,
) -> None:
    service, events = make_rebuild_service(
        tmp_path,
        ExampleProjectionBuilder(),
    )

    result = service.rebuild("example_projection", "source-1")

    assert result.projection_data.value == "source-1"
    assert result.reconstruction.model_dump() == {
        "projection_type": "example_projection",
        "reconstruction_source": "test_runtime_state",
        "rebuildable": True,
        "authoritative_source": "test_event_store",
    }
    assert [
        diagnostic.event_type for diagnostic in result.diagnostics
    ] == [
        "projection_rebuild_started",
        "projection_rebuild_completed",
    ]
    assert [
        event.type.value
        for event in events.list_persisted_events()
    ] == [
        "projection_rebuild_started",
        "projection_manifest_hash_computed",
        "projection_manifest_generated",
        "projection_rebuild_completed",
    ]
    assert result.snapshot_manifest.projection_name == "example_projection"
    assert result.snapshot_manifest.source_session_id == "source-1"
    assert len(result.snapshot_manifest.content_hash) == 64


def test_invalid_projection_rebuild_fails_with_structured_diagnostics(
    tmp_path,
) -> None:
    service, events = make_rebuild_service(
        tmp_path,
        InvalidExampleProjectionBuilder(),
    )

    with pytest.raises(ProjectionRebuildValidationError) as exc_info:
        service.rebuild("example_projection", "source-1")

    error = exc_info.value
    assert "metadata does not match" in str(error)
    assert [
        diagnostic.event_type for diagnostic in error.diagnostics
    ] == [
        "projection_rebuild_started",
        "projection_rebuild_failed",
    ]
    failed = error.diagnostics[-1]
    assert failed.projection_type == "example_projection"
    assert failed.schema_version == 1
    assert failed.builder_name == "ExampleProjectionBuilder"
    assert failed.source == "source-1"
    assert failed.reconstruction.reconstruction_source == "test_runtime_state"
    assert events.list_persisted_events()[-1].severity.value == "error"


def test_projection_rebuild_endpoint_rebuilds_registered_projection() -> None:
    session = runtime_session_service.create_session(
        "projection-rebuild-endpoint-task"
    )

    client = TestClient(app)
    response = client.post(
        "/runtime/projections/decision_projection/rebuild",
        json={"source": session.id},
    )
    repeated_response = client.post(
        "/runtime/projections/decision_projection/rebuild",
        json={"source": session.id},
    )

    assert response.status_code == 200
    assert repeated_response.status_code == 200
    body = response.json()
    repeated_body = repeated_response.json()
    assert repeated_body["projection_data"] == body["projection_data"]
    assert repeated_body["reconstruction"] == body["reconstruction"]
    assert repeated_body["snapshot_manifest"]["content_hash"] == (
        body["snapshot_manifest"]["content_hash"]
    )
    assert body["projection_type"] == "decision_projection"
    assert body["schema_version"] == 1
    assert body["builder_name"] == "DecisionProjectionBuilderService"
    assert body["source"] == session.id
    assert body["projection_data"] == []
    assert body["snapshot_manifest"]["projection_name"] == (
        "decision_projection"
    )
    assert body["snapshot_manifest"]["source_session_id"] == session.id
    assert len(body["snapshot_manifest"]["content_hash"]) == 64
    assert body["reconstruction"] == {
        "projection_type": "decision_projection",
        "reconstruction_source": "runtime_session_state",
        "rebuildable": True,
        "authoritative_source": "runtime_session",
    }
    assert [
        diagnostic["event_type"] for diagnostic in body["diagnostics"]
    ] == [
        "projection_rebuild_started",
        "projection_rebuild_completed",
    ]
    completed = event_service.list_persisted_events(
        event_type="projection_rebuild_completed"
    )
    assert len(completed) == 2
    assert {
        key: completed[0].metadata[key]
        for key in (
            "projection_type",
            "schema_version",
            "builder_name",
            "source",
            "reconstruction",
        )
    } == {
        "projection_type": "decision_projection",
        "schema_version": 1,
        "builder_name": "DecisionProjectionBuilderService",
        "source": session.id,
        "reconstruction": body["reconstruction"],
    }
    assert completed[0].metadata["projection_name"] == (
        "decision_projection"
    )
    assert completed[0].metadata["projection_version"] == 1
    assert completed[0].metadata["status"] == "completed"
    assert completed[0].metadata["duration_ms"] >= 0
    assert completed[0].metadata["rebuild_start_event_id"] >= 1


def test_projection_rebuild_endpoint_returns_invalid_output_diagnostics(
    monkeypatch,
) -> None:
    session = runtime_session_service.create_session(
        "invalid-projection-rebuild-endpoint-task"
    )

    def build_invalid(source: str) -> ExampleProjection:
        return InvalidExampleProjectionBuilder().build(source)

    monkeypatch.setattr(
        decision_projection_builder_service,
        "build",
        build_invalid,
    )

    response = TestClient(app).post(
        "/runtime/projections/decision_projection/rebuild",
        json={"source": session.id},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "metadata does not match" in detail["message"]
    assert [
        diagnostic["event_type"] for diagnostic in detail["diagnostics"]
    ] == [
        "projection_rebuild_started",
        "projection_rebuild_failed",
    ]
    assert detail["diagnostics"][-1]["projection_type"] == (
        "decision_projection"
    )


def test_projection_rebuild_endpoint_returns_clean_unknown_type_error() -> None:
    response = TestClient(app).post(
        "/runtime/projections/missing_projection/rebuild",
        json={"source": "session-1"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }
