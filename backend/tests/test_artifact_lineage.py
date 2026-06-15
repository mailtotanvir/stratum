from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.runtime.projection_registry import ProjectionRegistry
from app.services.artifact_lineage_projection_builder_service import (
    ArtifactLineageProjectionBuilder,
)
from app.services.artifact_lineage_service import ArtifactLineageService
from app.services.event_service import EventService, event_service
from app.services.projection_rebuild_service import ProjectionRebuildService
from app.services.trace_service import TraceService


BUILT_AT = datetime(2026, 6, 15, 16, 0, tzinfo=UTC)


def make_services(tmp_path):
    events = EventService(TraceService(tmp_path / "artifact_lineage.db"))
    builder = ArtifactLineageProjectionBuilder(
        events=events,
        clock=lambda: BUILT_AT,
    )
    return builder, ArtifactLineageService(builder, events), events


def emit_lineage_events(events: EventService) -> None:
    events.emit_event_sync(
        EventType.PROPOSAL_GENERATED,
        "Proposal generated",
        metadata={
            "proposal_id": "proposal-1",
            "source_type": "planner_recommendation",
            "source_id": "recommendation-1",
            "status": "proposed",
        },
    )
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Decision created",
        metadata={
            "decision_id": "decision-1",
            "session_id": "session-1",
            "decision_type": "recommendation_selection",
            "selected_entity_type": "planner_recommendation",
            "selected_entity_id": "recommendation-1",
        },
    )
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Parent artifact created",
        metadata={
            "artifact_id": "artifact-parent",
            "path": "reports/parent.md",
            "kind": "report",
            "task_id": "task-1",
            "created_at": "2026-06-15T15:00:00+00:00",
        },
    )
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Artifact created",
        metadata={
            "artifact_id": "artifact-1",
            "path": "reports/result.md",
            "kind": "report",
            "task_id": "task-1",
            "created_at": "2026-06-15T15:01:00+00:00",
            "metadata": {
                "parent_artifact_ids": ["artifact-parent"],
                "content": "must not enter lineage",
            },
        },
    )
    events.emit_event_sync(
        EventType.RUNTIME_ARTIFACT_ATTACHED,
        "Runtime artifact attached",
        metadata={
            "artifact_id": "artifact-1",
            "task_id": "task-1",
            "session_id": "session-1",
            "created_at": "2026-06-15T15:02:00+00:00",
        },
    )
    events.emit_event_sync(
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        "Proposal artifact attached",
        metadata={
            "artifact_id": "artifact-1",
            "proposal_id": "proposal-1",
            "created_at": "2026-06-15T15:03:00+00:00",
        },
    )
    events.emit_event_sync(
        EventType.TOOL_INVOCATION_COMPLETED,
        "Tool invocation completed",
        metadata={
            "tool_invocation_id": "invocation-1",
            "session_id": "session-1",
            "tool_id": "tool-1",
            "completed_at": "2026-06-15T15:04:00+00:00",
            "output_payload": {
                "artifacts": ["artifact-1"],
                "content": "must not enter lineage",
            },
        },
    )
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Artifact updated",
        metadata={
            "artifact_id": "artifact-1",
            "path": "reports/result-v2.md",
            "kind": "report",
            "updated_at": "2026-06-15T15:05:00+00:00",
        },
    )


def test_artifact_lineage_construction_and_update_folding(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    emit_lineage_events(events)

    projection = builder.build_read_only()
    record = next(
        record
        for record in projection.records
        if record.artifact_id == "artifact-1"
    )

    assert record.artifact_path == "reports/result-v2.md"
    assert record.artifact_type == "report"
    assert record.session_id == "session-1"
    assert record.producing_tool_invocation_id == "invocation-1"
    assert record.proposal_id == "proposal-1"
    assert record.decision_id == "decision-1"
    assert record.parent_artifact_ids == ["artifact-parent"]
    assert record.lineage_status == "linked"
    assert record.created_at.isoformat() == "2026-06-15T15:01:00+00:00"
    assert record.updated_at.isoformat() == "2026-06-15T15:05:00+00:00"
    assert "content" not in str(record.metadata)


def test_proposal_decision_and_tool_links_are_counted(tmp_path) -> None:
    builder, service, events = make_services(tmp_path)
    emit_lineage_events(events)

    summary = service.summary()

    assert summary.total_artifacts == 2
    assert summary.linked_artifacts == 1
    assert summary.orphaned_artifacts == 1
    assert summary.artifact_types == {"report": 2}
    assert summary.producing_tools == {"tool-1": 1}
    assert summary.decision_linked_artifacts == 1
    assert summary.proposal_linked_artifacts == 1
    assert summary.artifact_decision_links_total == 1
    assert summary.artifact_proposal_links_total == 1
    assert summary.artifact_tool_links_total == 1


def test_parent_artifact_chain_is_deterministic(tmp_path) -> None:
    _, service, events = make_services(tmp_path)
    emit_lineage_events(events)

    first = service.get_chain("artifact-1")
    second = service.get_chain("artifact-1")

    assert first == second
    assert [record.artifact_id for record in first.records] == [
        "artifact-parent",
        "artifact-1",
    ]
    assert first.complete is True


def test_replay_reconstruction_is_identical(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    emit_lineage_events(events)
    registry = ProjectionRegistry()
    registry.register(builder)
    rebuilds = ProjectionRebuildService(registry=registry, events=events)

    first = rebuilds.rebuild("artifact_lineage_projection", "event_store")
    first_records = first.projection_data.records
    second = rebuilds.rebuild("artifact_lineage_projection", "event_store")

    assert second.projection_data.records == first_records
    assert len(
        events.list_persisted_events(
            event_type="artifact_lineage_rebuilt"
        )
    ) == 2


def test_missing_creation_and_parent_are_incomplete(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    events.emit_event_sync(
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        "Incomplete artifact link",
        metadata={
            "artifact_id": "missing-artifact",
            "proposal_id": "missing-proposal",
        },
    )
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Artifact with missing parent",
        metadata={
            "artifact_id": "child",
            "path": "child.txt",
            "kind": "file",
            "parent_artifact_ids": ["missing-parent"],
        },
    )

    projection = builder.build_read_only()
    by_id = {record.artifact_id: record for record in projection.records}

    assert by_id["missing-artifact"].lineage_status == "incomplete"
    assert by_id["missing-artifact"].metadata["incomplete_reasons"] == [
        "missing_artifact_creation",
        "missing_proposal",
    ]
    assert by_id["child"].metadata["incomplete_reasons"] == [
        "missing_parent_artifact"
    ]


def test_malformed_artifact_metadata_allows_partial_reconstruction(
    tmp_path,
) -> None:
    builder, _, events = make_services(tmp_path)
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Malformed event",
        metadata={"path": "missing-id.txt"},
    )
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Partially malformed artifact",
        metadata={
            "artifact_id": "partial",
            "path": 42,
            "kind": ["invalid"],
            "created_at": "not-a-timestamp",
            "metadata": {"content": "excluded"},
        },
    )

    projection = builder.build_read_only()

    assert projection.incomplete_event_ids == [1]
    assert projection.records[0].artifact_id == "partial"
    assert projection.records[0].lineage_status == "incomplete"
    assert projection.records[0].metadata["incomplete_reasons"] == [
        "invalid_artifact_type",
        "invalid_created_at",
        "missing_artifact_path",
    ]
    assert "excluded" not in str(projection.records[0].metadata)


def test_rebuild_emits_incomplete_diagnostics(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    events.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Orphan artifact",
        metadata={
            "artifact_id": "orphan",
            "path": "orphan.txt",
            "kind": "file",
        },
    )

    builder.build("event_store")

    assert [
        event.type.value
        for event in events.list_persisted_events()
        if event.type.value.startswith("artifact_lineage_")
    ] == [
        "artifact_lineage_updated",
        "artifact_lineage_incomplete",
        "artifact_lineage_rebuilt",
    ]


def test_reconstruction_failure_emits_diagnostic(tmp_path) -> None:
    events = EventService(TraceService(tmp_path / "failure.db"))

    def fail_clock():
        raise RuntimeError("clock unavailable")

    builder = ArtifactLineageProjectionBuilder(
        events=events,
        clock=fail_clock,
    )

    with pytest.raises(RuntimeError, match="clock unavailable"):
        builder.build("event_store")

    failures = events.list_persisted_events(
        event_type="artifact_lineage_reconstruction_failed"
    )
    assert len(failures) == 1
    assert failures[0].severity.value == "error"


def test_artifact_lineage_routes() -> None:
    emit_lineage_events(event_service)
    client = TestClient(app)

    listing = client.get("/runtime/artifact-lineage")
    detail = client.get("/runtime/artifact-lineage/artifact-1")
    events = client.get("/runtime/artifact-lineage/artifact-1/events")
    summary = client.get("/runtime/artifact-lineage/summary")

    assert listing.status_code == 200
    assert [record["artifact_id"] for record in listing.json()] == [
        "artifact-1",
        "artifact-parent",
    ]
    assert detail.status_code == 200
    assert [
        record["artifact_id"] for record in detail.json()["records"]
    ] == ["artifact-parent", "artifact-1"]
    assert events.status_code == 200
    assert events.json()["event_count"] == 7
    assert all("metadata" not in event for event in events.json()["events"])
    assert summary.status_code == 200
    assert summary.json()["total_artifacts"] == 2


def test_artifact_lineage_route_returns_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/artifact-lineage/missing-artifact"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Artifact lineage not found: missing-artifact"
    }
