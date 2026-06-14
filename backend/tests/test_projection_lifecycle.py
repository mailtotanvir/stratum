from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    Projection,
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType
from app.runtime.projection_registry import ProjectionRegistry
from app.services.event_service import EventService
from app.services.projection_lifecycle_service import (
    ProjectionLifecycleService,
)
from app.services.projection_rebuild_service import (
    ProjectionRebuildService,
    ProjectionRebuildValidationError,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


STARTED_AT = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


class LifecycleProjection(Projection):
    value: str


class LifecycleProjectionBuilder:
    projection_type = "lifecycle_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=3,
        builder_name="LifecycleProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )

    def build(self, source: str) -> LifecycleProjection:
        return LifecycleProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=STARTED_AT,
                source="lifecycle_projection_builder",
            ),
            value=source,
        )


class InvalidLifecycleProjectionBuilder(LifecycleProjectionBuilder):
    def build(self, source: str) -> LifecycleProjection:
        projection = super().build(source)
        return projection.model_copy(
            update={
                "metadata": projection.metadata.model_copy(
                    update={"schema_version": 4}
                )
            }
        )


def make_services(tmp_path, builder, clock_values):
    registry = ProjectionRegistry()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "lifecycle.db"))
    lifecycle = ProjectionLifecycleService(
        registry=registry,
        events=events,
        clock=lambda: next(clock_values),
    )
    rebuilds = ProjectionRebuildService(
        registry=registry,
        events=events,
        lifecycle=lifecycle,
    )
    return rebuilds, lifecycle, events


def test_projection_lifecycle_tracks_completed_rebuild(tmp_path) -> None:
    completed_at = STARTED_AT + timedelta(milliseconds=125)
    rebuilds, lifecycle, events = make_services(
        tmp_path,
        LifecycleProjectionBuilder(),
        iter([STARTED_AT, completed_at]),
    )
    events.emit_event_sync(
        EventType.RUNTIME_SESSION_CREATED,
        "Source event one",
        metadata={"session_id": "session-1"},
    )
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Source event two",
        metadata={"session_id": "session-1"},
    )

    rebuilds.rebuild("lifecycle_projection", "session-1")
    history = lifecycle.rebuild_history()

    assert history.total_count == 1
    assert history.rebuilds[0].model_dump() == {
        "projection_name": "lifecycle_projection",
        "projection_version": 3,
        "rebuild_started_at": STARTED_AT,
        "rebuild_completed_at": completed_at,
        "status": "completed",
        "source_event_count": 2,
        "source_event_range_start": 1,
        "source_event_range_end": 2,
        "duration_ms": 125.0,
    }
    assert lifecycle.projection_statuses()[0].model_dump() == {
        "projection_name": "lifecycle_projection",
        "projection_version": 3,
        "latest_rebuild_status": "completed",
        "latest_rebuild_started_at": STARTED_AT,
        "latest_rebuild_completed_at": completed_at,
        "latest_rebuild_duration_ms": 125.0,
    }


def test_projection_lifecycle_tracks_failed_rebuild(tmp_path) -> None:
    failed_at = STARTED_AT + timedelta(milliseconds=50)
    rebuilds, lifecycle, _ = make_services(
        tmp_path,
        InvalidLifecycleProjectionBuilder(),
        iter([STARTED_AT, failed_at]),
    )

    with pytest.raises(ProjectionRebuildValidationError):
        rebuilds.rebuild("lifecycle_projection", "session-1")

    record = lifecycle.rebuild_history().rebuilds[0]
    assert record.status == "failed"
    assert record.duration_ms == 50.0
    assert record.rebuild_completed_at == failed_at


def test_projection_lifecycle_history_is_newest_first(tmp_path) -> None:
    second_start = STARTED_AT + timedelta(seconds=1)
    rebuilds, lifecycle, _ = make_services(
        tmp_path,
        LifecycleProjectionBuilder(),
        iter(
            [
                STARTED_AT,
                STARTED_AT + timedelta(milliseconds=10),
                second_start,
                second_start + timedelta(milliseconds=20),
            ]
        ),
    )

    rebuilds.rebuild("lifecycle_projection", "session-1")
    rebuilds.rebuild("lifecycle_projection", "session-2")

    history = lifecycle.rebuild_history()
    assert [
        record.rebuild_started_at for record in history.rebuilds
    ] == [second_start, STARTED_AT]
    assert [record.duration_ms for record in history.rebuilds] == [
        20.0,
        10.0,
    ]


def test_projection_lifecycle_queries_do_not_emit_events(tmp_path) -> None:
    _, lifecycle, events = make_services(
        tmp_path,
        LifecycleProjectionBuilder(),
        iter([]),
    )

    before = events.list_persisted_events()
    lifecycle.rebuild_history()
    lifecycle.projection_statuses()

    assert events.list_persisted_events() == before


def test_projection_lifecycle_reconstructs_legacy_events(tmp_path) -> None:
    _, lifecycle, events = make_services(
        tmp_path,
        LifecycleProjectionBuilder(),
        iter([]),
    )
    metadata = {
        "projection_type": "lifecycle_projection",
        "schema_version": 3,
        "builder_name": "LifecycleProjectionBuilder",
        "source": "session-1",
    }
    events.emit_event_sync(
        EventType.PROJECTION_REBUILD_STARTED,
        "Projection rebuild started",
        metadata=metadata,
    )
    events.emit_event_sync(
        EventType.PROJECTION_REBUILD_COMPLETED,
        "Projection rebuild completed",
        metadata=metadata,
    )

    record = lifecycle.rebuild_history().rebuilds[0]

    assert record.projection_name == "lifecycle_projection"
    assert record.projection_version == 3
    assert record.status == "completed"
    assert record.rebuild_completed_at is not None
    assert record.duration_ms is not None


def test_projection_lifecycle_routes_expose_status_and_history() -> None:
    session = runtime_session_service.create_session(
        "projection-lifecycle-route-task"
    )
    client = TestClient(app)

    rebuild = client.post(
        "/runtime/projections/decision_projection/rebuild",
        json={"source": session.id},
    )
    discovery = client.get("/runtime/projections")
    history = client.get("/runtime/projections/history")

    assert rebuild.status_code == 200
    assert discovery.status_code == 200
    statuses = {
        item["projection_name"]: item
        for item in discovery.json()["projections"]
    }
    assert statuses["decision_projection"]["projection_version"] == 1
    assert statuses["decision_projection"]["latest_rebuild_status"] == (
        "completed"
    )
    assert history.status_code == 200
    body = history.json()
    assert body["total_count"] == 1
    assert body["rebuilds"][0]["projection_name"] == (
        "decision_projection"
    )
    assert body["rebuilds"][0]["status"] == "completed"
