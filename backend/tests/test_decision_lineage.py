from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.runtime.projection_registry import ProjectionRegistry
from app.services.decision_lineage_projection_builder_service import (
    DecisionLineageProjectionBuilder,
)
from app.services.decision_lineage_service import DecisionLineageService
from app.services.event_service import EventService, event_service
from app.services.projection_rebuild_service import ProjectionRebuildService
from app.services.trace_service import TraceService


BUILT_AT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def make_services(tmp_path):
    events = EventService(TraceService(tmp_path / "decision_lineage.db"))
    builder = DecisionLineageProjectionBuilder(
        events=events,
        clock=lambda: BUILT_AT,
    )
    return builder, DecisionLineageService(builder, events), events


def emit_lineage_events(events: EventService) -> None:
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_CREATED,
        "Recommendation created",
        metadata={
            "recommendation_id": "recommendation-1",
            "session_id": "session-1",
            "created_at": "2026-06-15T10:00:00+00:00",
        },
    )
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
        "Root decision",
        metadata={
            "decision_id": "decision-1",
            "session_id": "session-1",
            "decision_type": "recommendation_selection",
            "selected_entity_id": "recommendation-1",
            "selected_entity_type": "planner_recommendation",
            "created_at": "2026-06-15T10:01:00+00:00",
        },
    )
    events.emit_event_sync(
        EventType.DECISION_EVIDENCE_CREATED,
        "Evidence created",
        metadata={
            "decision_id": "decision-1",
            "evidence_id": "evidence-1",
            "evidence_type": "recommendation",
            "evidence_reference": "recommendation-1",
            "summary": "Recommendation evidence",
        },
    )
    events.emit_event_sync(
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        "Artifact attached",
        metadata={
            "proposal_id": "proposal-1",
            "artifact_id": "artifact-1",
        },
    )
    events.emit_event_sync(
        EventType.PROPOSAL_RESOLVED,
        "Proposal approved",
        metadata={
            "proposal_id": "proposal-1",
            "source_type": "planner_recommendation",
            "source_id": "recommendation-1",
            "status": "approved",
        },
    )
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Child decision",
        metadata={
            "decision_id": "decision-2",
            "session_id": "session-1",
            "decision_type": "follow_up",
            "parent_decision_id": "decision-1",
            "created_at": "2026-06-15T10:02:00+00:00",
        },
    )


def test_lineage_construction_and_evidence_linking(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    emit_lineage_events(events)

    projection = builder.build_read_only()

    assert [record.decision_id for record in projection.records] == [
        "decision-1",
        "decision-2",
    ]
    root = projection.records[0]
    assert root.recommendation_id == "recommendation-1"
    assert root.proposal_id == "proposal-1"
    assert root.outcome == "approved"
    assert root.evidence_count == 1
    assert root.related_artifact_ids == ["artifact-1"]
    assert root.source_event_ids == [1, 2, 3, 4, 5, 6]
    assert root.metadata["orphaned"] is False


def test_parent_child_lineage_and_summary(tmp_path) -> None:
    builder, service, events = make_services(tmp_path)
    emit_lineage_events(events)

    chain = service.get_chain("decision-2")
    summary = service.summary()

    assert [record.decision_id for record in chain.records] == [
        "decision-1",
        "decision-2",
    ]
    assert chain.complete is True
    assert chain.records[-1].lineage_depth == 1
    assert summary.total_decisions == 2
    assert summary.total_lineage_chains == 1
    assert summary.average_lineage_depth == 0.5
    assert summary.lineage_max_depth == 1
    assert summary.evidence_links_total == 1


def test_replay_reconstruction_is_deterministic(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    emit_lineage_events(events)
    registry = ProjectionRegistry()
    registry.register(builder)
    rebuilds = ProjectionRebuildService(registry=registry, events=events)

    first = rebuilds.rebuild("decision_lineage_projection", "event_store")
    first_records = first.projection_data.records
    second = rebuilds.rebuild("decision_lineage_projection", "event_store")

    assert second.projection_data.records == first_records
    assert len(
        events.list_persisted_events(
            event_type="decision_lineage_rebuilt"
        )
    ) == 2


def test_missing_references_are_flagged_as_orphans(tmp_path) -> None:
    builder, service, events = make_services(tmp_path)
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Incomplete decision",
        metadata={
            "decision_id": "orphan",
            "session_id": "session-1",
            "decision_type": "recommendation_selection",
            "selected_entity_type": "planner_recommendation",
            "selected_entity_id": "missing-recommendation",
            "proposal_id": "missing-proposal",
            "parent_decision_id": "missing-parent",
        },
    )

    record = builder.build_read_only().records[0]

    assert record.metadata["orphaned"] is True
    assert record.metadata["incomplete_reasons"] == [
        "missing_parent_decision",
        "missing_proposal",
        "missing_recommendation",
    ]
    assert service.summary().orphaned_decisions == 1


def test_malformed_metadata_allows_partial_reconstruction(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Malformed decision without id",
        metadata={"decision_type": "unknown"},
    )
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Decision with malformed optional metadata",
        metadata={
            "decision_id": "partial",
            "decision_type": "unknown",
            "created_at": "not-a-timestamp",
            "related_proposal_ids": "not-a-list",
        },
    )

    projection = builder.build_read_only()

    assert projection.incomplete_event_ids == [1]
    assert [record.decision_id for record in projection.records] == [
        "partial"
    ]
    assert projection.records[0].metadata["incomplete_reasons"] == [
        "invalid_related_proposal_ids",
        "invalid_selected_at",
    ]


def test_incomplete_rebuild_emits_lineage_diagnostics(tmp_path) -> None:
    builder, _, events = make_services(tmp_path)
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Orphan decision",
        metadata={
            "decision_id": "orphan",
            "decision_type": "unknown",
            "parent_decision_id": "missing",
        },
    )

    builder.build("event_store")

    assert [
        event.type.value
        for event in events.list_persisted_events()
        if event.type.value.startswith("decision_lineage_")
    ] == [
        "decision_lineage_updated",
        "decision_lineage_incomplete",
        "decision_lineage_rebuilt",
    ]


def test_reconstruction_failure_emits_diagnostic(tmp_path) -> None:
    events = EventService(TraceService(tmp_path / "failure.db"))

    def fail_clock():
        raise RuntimeError("clock unavailable")

    builder = DecisionLineageProjectionBuilder(
        events=events,
        clock=fail_clock,
    )

    with pytest.raises(RuntimeError, match="clock unavailable"):
        builder.build("event_store")

    failures = events.list_persisted_events(
        event_type="decision_lineage_reconstruction_failed"
    )
    assert len(failures) == 1
    assert failures[0].severity.value == "error"


def test_lineage_routes() -> None:
    emit_lineage_events(event_service)
    client = TestClient(app)

    listing = client.get("/runtime/decision-lineage")
    detail = client.get("/runtime/decision-lineage/decision-2")
    evidence = client.get(
        "/runtime/decision-lineage/decision-1/evidence"
    )
    summary = client.get("/runtime/decision-lineage/summary")

    assert listing.status_code == 200
    assert [record["decision_id"] for record in listing.json()] == [
        "decision-2",
        "decision-1",
    ]
    assert detail.status_code == 200
    assert [
        record["decision_id"] for record in detail.json()["records"]
    ] == ["decision-1", "decision-2"]
    assert evidence.status_code == 200
    assert evidence.json()["evidence_count"] == 1
    assert summary.status_code == 200
    assert summary.json()["total_decisions"] == 2


def test_lineage_route_returns_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/decision-lineage/missing-decision"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Decision lineage not found: missing-decision"
    }
