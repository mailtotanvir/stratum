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
from app.services.event_service import EventService, event_service
from app.services.projection_snapshot_manifest_service import (
    ProjectionManifestGenerationError,
    ProjectionSnapshotManifestService,
    stable_projection_content_hash,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


class ManifestProjection(Projection):
    value: str


class ManifestProjectionBuilder:
    projection_type = "manifest_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=3,
        builder_name="ManifestProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_session_state",
            authoritative_source="runtime_session",
        ),
    )

    def __init__(self, value: str = "stable") -> None:
        self.value = value

    def build(self, source: str) -> ManifestProjection:
        return ManifestProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
                source="manifest_projection_builder",
            ),
            value=self.value,
        )


class FailingManifestProjectionBuilder(ManifestProjectionBuilder):
    def build(self, source: str) -> ManifestProjection:
        raise RuntimeError("manifest projection unavailable")


def make_manifest_service(
    tmp_path,
    builder: ManifestProjectionBuilder,
) -> tuple[ProjectionSnapshotManifestService, EventService]:
    registry = ProjectionRegistry()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_manifest.db"))
    return (
        ProjectionSnapshotManifestService(
            registry=registry,
            events=events,
            clock=lambda: datetime(2026, 6, 11, 13, 0, tzinfo=UTC),
        ),
        events,
    )


def test_manifest_generation_describes_projection_and_sources(tmp_path) -> None:
    builder = ManifestProjectionBuilder()
    service, events = make_manifest_service(tmp_path, builder)
    events.emit_event_sync(
        event_type="planner_completed",
        message="Source event",
        metadata={"session_id": "session-1"},
    )

    manifest = service.generate(
        builder.schema_info,
        builder.build("session-1"),
        "session-1",
    )

    assert manifest.model_dump(mode="json") == {
        "projection_name": "manifest_projection",
        "schema_version": 3,
        "builder_name": "ManifestProjectionBuilder",
        "generated_at": "2026-06-11T13:00:00Z",
        "source_event_count": 1,
        "source_session_id": "session-1",
        "source_runtime_id": None,
        "reconstruction_info": {
            "projection_type": "manifest_projection",
            "reconstruction_source": "runtime_session_state",
            "rebuildable": True,
            "authoritative_source": "runtime_session",
        },
        "verification_status": None,
        "content_hash": stable_projection_content_hash(
            builder.build("session-1")
        ),
    }
    assert [
        event.type.value for event in events.list_persisted_events()
    ][-2:] == [
        "projection_manifest_hash_computed",
        "projection_manifest_generated",
    ]


def test_projection_content_hash_is_deterministic() -> None:
    first = {"beta": [2, 1], "alpha": {"value": True}}
    second = {"alpha": {"value": True}, "beta": [2, 1]}

    assert stable_projection_content_hash(first) == (
        stable_projection_content_hash(second)
    )


def test_projection_content_hash_changes_with_content() -> None:
    assert stable_projection_content_hash({"value": "first"}) != (
        stable_projection_content_hash({"value": "second"})
    )


def test_projection_content_hash_excludes_volatile_fields_by_default() -> None:
    first = {
        "generated_at": "2026-06-11T12:00:00Z",
        "metadata": {"built_at": "2026-06-11T12:00:00Z"},
        "value": "stable",
    }
    second = {
        "generated_at": "2026-06-12T12:00:00Z",
        "metadata": {"built_at": "2026-06-12T12:00:00Z"},
        "value": "stable",
    }

    assert stable_projection_content_hash(first) == (
        stable_projection_content_hash(second)
    )
    assert stable_projection_content_hash(
        first,
        include_volatile=True,
    ) != stable_projection_content_hash(
        second,
        include_volatile=True,
    )


def test_manifest_generation_failure_emits_diagnostic(tmp_path) -> None:
    service, events = make_manifest_service(
        tmp_path,
        FailingManifestProjectionBuilder(),
    )

    with pytest.raises(
        ProjectionManifestGenerationError,
        match="manifest projection unavailable",
    ):
        service.current_manifest("manifest_projection", "session-1")

    failed = events.list_persisted_events(
        event_type="projection_manifest_generation_failed"
    )
    assert len(failed) == 1
    assert failed[0].severity.value == "error"


def test_projection_manifest_endpoint_returns_current_manifest() -> None:
    session = runtime_session_service.create_session(
        "projection-manifest-endpoint-task"
    )
    event_service.emit_event_sync(
        event_type="planner_completed",
        message="Manifest source event",
        metadata={"session_id": session.id},
    )

    response = TestClient(app).get(
        "/projections/decision_projection/manifest",
        params={"source": session.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_name"] == "decision_projection"
    assert body["source_session_id"] == session.id
    assert body["source_event_count"] == 1
    assert body["source_runtime_id"] is None
    assert len(body["content_hash"]) == 64


def test_projection_manifest_endpoint_returns_unknown_projection() -> None:
    response = TestClient(app).get(
        "/projections/missing_projection/manifest",
        params={"source": "session-1"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }
