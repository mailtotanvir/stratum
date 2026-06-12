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
from app.runtime.projection_registry import ProjectionRegistry
from app.services.event_service import EventService, event_service
from app.services.projection_snapshot_export_service import (
    ProjectionSnapshotExportError,
    ProjectionSnapshotExportService,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.trace_service import TraceService


class ExportProjection(Projection):
    value: str


class ExportProjectionBuilder:
    projection_type = "export_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=2,
        builder_name="ExportProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_session_state",
            authoritative_source="runtime_session",
        ),
    )

    def __init__(self) -> None:
        self.build_count = 0

    def build(self, source: str) -> ExportProjection:
        built_at = datetime(2026, 6, 11, 12, 0, tzinfo=UTC) + timedelta(
            minutes=self.build_count
        )
        self.build_count += 1
        return ExportProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=built_at,
                source="export_projection_builder",
            ),
            value=source,
        )


class FailingExportProjectionBuilder(ExportProjectionBuilder):
    def build(self, source: str) -> ExportProjection:
        raise RuntimeError("projection export unavailable")


def make_export_service(tmp_path):
    registry = ProjectionRegistry()
    builder = ExportProjectionBuilder()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_export.db"))
    sessions = RuntimeSessionService(tmp_path / "runtime_sessions.db")
    session = sessions.create_session("projection-export-task")
    export_times = iter(
        [
            datetime(2026, 6, 11, 13, 0, tzinfo=UTC),
            datetime(2026, 6, 11, 13, 1, tzinfo=UTC),
        ]
    )
    export_ids = iter(["export-1", "export-2"])
    service = ProjectionSnapshotExportService(
        registry=registry,
        events=events,
        sessions=sessions,
        clock=lambda: next(export_times),
        id_factory=lambda: next(export_ids),
    )
    return service, builder, events, sessions, session


def stable_export_content(export) -> dict:
    content = export.model_dump(mode="json")
    content.pop("export_id")
    content.pop("exported_at")
    for diagnostic in content["diagnostics"]:
        diagnostic.pop("export_id")
    return content


def test_projection_snapshot_export_is_complete_and_deterministic(
    tmp_path,
) -> None:
    service, _, events, _, session = make_export_service(tmp_path)

    first = service.export("export_projection", session.id)
    second = service.export("export_projection", session.id)

    assert first.projection_name == "export_projection"
    assert first.projection == {
        "metadata": {
            "projection_type": "export_projection",
            "schema_version": 2,
            "builder_name": "ExportProjectionBuilder",
            "reconstruction": {
                "projection_type": "export_projection",
                "reconstruction_source": "runtime_session_state",
                "rebuildable": True,
                "authoritative_source": "runtime_session",
            },
            "source": "export_projection_builder",
        },
        "value": session.id,
    }
    assert first.snapshot_manifest.projection_name == "export_projection"
    assert first.snapshot_manifest.source_session_id == session.id
    assert first.snapshot_manifest.generated_at == session.created_at
    assert first.snapshot_manifest.content_hash == (
        second.snapshot_manifest.content_hash
    )
    assert first.reconstruction_info == (
        ExportProjectionBuilder.schema_info.reconstruction
    )
    assert first.verification_status is None
    assert first.lineage is not None
    assert first.lineage.projection_name == "export_projection"
    assert first.lineage.source_identifiers["session_id"] == session.id
    assert first.lineage.reconstruction_info == (
        ExportProjectionBuilder.schema_info.reconstruction.model_dump()
    )
    assert stable_export_content(first) == stable_export_content(second)

    export_events = [
        event
        for event in events.list_persisted_events()
        if event.type.value.startswith("projection_snapshot_export_")
    ]
    assert [event.type.value for event in export_events] == [
        "projection_snapshot_export_started",
        "projection_snapshot_export_completed",
        "projection_snapshot_export_started",
        "projection_snapshot_export_completed",
    ]
    assert export_events[1].metadata == {
        "projection_name": "export_projection",
        "export_id": "export-1",
        "schema_version": 2,
        "builder_name": "ExportProjectionBuilder",
        "content_hash": first.snapshot_manifest.content_hash,
    }


def test_projection_snapshot_export_does_not_mutate_session_state(
    tmp_path,
) -> None:
    service, _, _, sessions, session = make_export_service(tmp_path)
    before = sessions.get_session(session.id)

    service.export("export_projection", session.id)

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


def test_projection_snapshot_export_failure_emits_diagnostic(tmp_path) -> None:
    registry = ProjectionRegistry()
    registry.register(FailingExportProjectionBuilder())
    events = EventService(TraceService(tmp_path / "failed_export.db"))
    service = ProjectionSnapshotExportService(
        registry=registry,
        events=events,
        id_factory=lambda: "failed-export",
    )

    with pytest.raises(
        ProjectionSnapshotExportError,
        match="projection export unavailable",
    ):
        service.export("export_projection", "session-1")

    failed = events.list_persisted_events(
        event_type="projection_snapshot_export_failed"
    )
    assert len(failed) == 1
    assert failed[0].severity.value == "error"
    assert failed[0].metadata == {
        "projection_name": "export_projection",
        "export_id": "failed-export",
        "schema_version": 2,
        "builder_name": "ExportProjectionBuilder",
        "content_hash": None,
    }


def test_projection_snapshot_export_endpoint_returns_portable_object() -> None:
    session = runtime_session_service.create_session(
        "projection-export-endpoint-task"
    )

    response = TestClient(app).post(
        "/projections/decision_projection/export",
        json={"source": session.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_name"] == "decision_projection"
    assert body["projection"] == []
    assert body["snapshot_manifest"]["source_session_id"] == session.id
    assert len(body["snapshot_manifest"]["content_hash"]) == 64
    assert body["reconstruction_info"] == {
        "projection_type": "decision_projection",
        "reconstruction_source": "runtime_session_state",
        "rebuildable": True,
        "authoritative_source": "runtime_session",
    }
    assert body["verification_status"] is None
    assert body["lineage"]["projection_name"] == "decision_projection"
    assert body["lineage"]["source_identifiers"]["session_id"] == session.id
    assert [
        diagnostic["event_type"] for diagnostic in body["diagnostics"]
    ] == [
        "projection_snapshot_export_started",
        "projection_snapshot_export_completed",
    ]
    completed = event_service.list_persisted_events(
        event_type="projection_snapshot_export_completed"
    )
    assert len(completed) == 1
    assert completed[0].metadata["content_hash"] == (
        body["snapshot_manifest"]["content_hash"]
    )


def test_projection_snapshot_export_endpoint_can_verify() -> None:
    session = runtime_session_service.create_session(
        "verified-projection-export-endpoint-task"
    )

    response = TestClient(app).post(
        "/projections/decision_projection/export",
        json={"source": session.id, "verify": True},
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"
    assert response.json()["snapshot_manifest"]["verification_status"] == (
        "verified"
    )


def test_projection_snapshot_export_can_exclude_lineage() -> None:
    session = runtime_session_service.create_session(
        "projection-export-without-lineage-task"
    )

    response = TestClient(app).post(
        "/projections/decision_projection/export",
        json={"source": session.id, "include_lineage": False},
    )

    assert response.status_code == 200
    assert response.json()["lineage"] is None


def test_projection_snapshot_export_endpoint_returns_unknown_projection() -> None:
    response = TestClient(app).post(
        "/projections/missing_projection/export",
        json={"source": "session-1"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }
