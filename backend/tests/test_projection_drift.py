from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.projection_replay import ProjectionReplayRequest
from app.models.runtime_event import EventType
from app.runtime.projection_registry import ProjectionRegistry
from app.services.event_service import EventService
from app.services.projection_drift_service import (
    ProjectionDriftCheckError,
    ProjectionDriftService,
)
from app.services.projection_fingerprint import (
    projection_state_fingerprint,
)
from app.services.projection_lifecycle_service import (
    ProjectionLifecycleService,
)
from app.services.projection_replay_service import (
    EventTypeProjectionReplayAdapter,
    ProjectionReplayService,
)
from app.services.trace_service import TraceService


BASE_TIME = datetime(2026, 6, 14, 16, 0, tzinfo=UTC)


class DriftProjectionBuilder:
    projection_type = "drift_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=4,
        builder_name="DriftProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )

    def __init__(self) -> None:
        self.build_calls: list[str] = []

    def build(self, source: str):
        self.build_calls.append(source)
        raise AssertionError("drift checks must not build projections")


class FailingAdapter:
    def accepts(self, event) -> bool:
        return True

    def apply(self, state, event) -> None:
        raise RuntimeError("replay state unavailable")


def make_drift_services(
    tmp_path,
    *,
    replay_clock,
    drift_clock,
    adapter=None,
):
    builder = DriftProjectionBuilder()
    registry = ProjectionRegistry()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_drift.db"))
    replay = ProjectionReplayService(
        registry=registry,
        events=events,
        adapters={
            "drift_projection": adapter
            or EventTypeProjectionReplayAdapter(
                frozenset({EventType.DECISION_RECORD_CREATED})
            )
        },
        clock=replay_clock,
    )
    drift = ProjectionDriftService(
        registry=registry,
        events=events,
        replay=replay,
        clock=drift_clock,
    )
    lifecycle = ProjectionLifecycleService(
        registry=registry,
        events=events,
    )
    return replay, drift, lifecycle, events, builder


def emit_decision(events: EventService, name: str) -> None:
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        name,
        metadata={"decision_id": name},
    )


def test_projection_drift_reports_no_drift(tmp_path) -> None:
    replay, drift, _, events, builder = make_drift_services(
        tmp_path,
        replay_clock=iter(
            [
                BASE_TIME,
                BASE_TIME + timedelta(milliseconds=5),
            ]
        ).__next__,
        drift_clock=iter(
            [
                BASE_TIME + timedelta(seconds=1),
                BASE_TIME + timedelta(seconds=1, milliseconds=3),
            ]
        ).__next__,
    )
    emit_decision(events, "decision-1")
    replay.replay(
        ProjectionReplayRequest(projection_name="drift_projection")
    )

    result = drift.check_projection("drift_projection")

    assert result.status == "in_sync"
    assert result.drift_detected is False
    assert result.source_event_count == 1
    assert result.persisted_projection_fingerprint == (
        result.replay_projection_fingerprint
    )
    assert result.mismatch_summary == []
    assert result.duration_ms == 3.0
    assert builder.build_calls == []


def test_projection_drift_detects_changed_event_state(tmp_path) -> None:
    replay, drift, _, events, _ = make_drift_services(
        tmp_path,
        replay_clock=iter(
            [BASE_TIME, BASE_TIME + timedelta(milliseconds=5)]
        ).__next__,
        drift_clock=iter(
            [
                BASE_TIME + timedelta(seconds=1),
                BASE_TIME + timedelta(seconds=1, milliseconds=2),
            ]
        ).__next__,
    )
    emit_decision(events, "decision-1")
    replay.replay(
        ProjectionReplayRequest(projection_name="drift_projection")
    )
    emit_decision(events, "decision-2")

    result = drift.check_projection("drift_projection")

    assert result.status == "drifted"
    assert result.drift_detected is True
    assert result.source_event_count == 2
    assert result.persisted_projection_fingerprint != (
        result.replay_projection_fingerprint
    )
    detected = events.list_persisted_events(
        event_type="projection_drift_detected"
    )
    assert detected[-1].metadata["drift_detected"] is True


def test_projection_fingerprint_is_deterministic_and_ignores_timestamps() -> None:
    first = {
        "items": [{"beta": 2, "alpha": 1}],
        "generated_at": "2026-06-14T00:00:00Z",
    }
    second = {
        "generated_at": "2027-01-01T00:00:00Z",
        "items": [{"alpha": 1, "beta": 2}],
    }

    assert projection_state_fingerprint(first) == (
        projection_state_fingerprint(second)
    )
    assert projection_state_fingerprint(first) != (
        projection_state_fingerprint(
            {"items": [{"alpha": 1, "beta": 3}]}
        )
    )


def test_projection_drift_check_does_not_mutate_lifecycle_or_build(
    tmp_path,
) -> None:
    replay, drift, lifecycle, events, builder = make_drift_services(
        tmp_path,
        replay_clock=iter(
            [BASE_TIME, BASE_TIME + timedelta(milliseconds=1)]
        ).__next__,
        drift_clock=iter(
            [
                BASE_TIME + timedelta(seconds=1),
                BASE_TIME + timedelta(seconds=1, milliseconds=1),
            ]
        ).__next__,
    )
    emit_decision(events, "decision-1")
    replay.replay(
        ProjectionReplayRequest(projection_name="drift_projection")
    )
    history_before = lifecycle.rebuild_history()

    drift.check_projection("drift_projection")

    assert lifecycle.rebuild_history() == history_before
    assert builder.build_calls == []
    assert not events.list_persisted_events(
        event_type="projection_rebuild_started"
    )


def test_projection_drift_failure_is_reported(tmp_path) -> None:
    _, drift, _, events, builder = make_drift_services(
        tmp_path,
        adapter=FailingAdapter(),
        replay_clock=iter([]).__next__,
        drift_clock=iter(
            [
                BASE_TIME,
                BASE_TIME + timedelta(milliseconds=4),
            ]
        ).__next__,
    )
    emit_decision(events, "decision-1")

    with pytest.raises(
        ProjectionDriftCheckError,
        match="replay state unavailable",
    ) as exc_info:
        drift.check_projection("drift_projection")

    assert exc_info.value.result.status == "failed"
    assert exc_info.value.result.duration_ms == 4.0
    assert builder.build_calls == []
    failed = events.list_persisted_events(
        event_type="projection_drift_check_failed"
    )
    assert failed[-1].severity.value == "error"


def test_single_projection_drift_route() -> None:
    client = TestClient(app)
    replay = client.post(
        "/runtime/projections/replay",
        json={"projection_name": "decision_projection"},
    )

    response = client.get(
        "/runtime/projections/decision_projection/drift"
    )

    assert replay.status_code == 200
    assert response.status_code == 200
    assert response.json()["projection_name"] == "decision_projection"
    assert response.json()["status"] == "in_sync"


def test_all_projections_drift_route_is_deterministic() -> None:
    response = TestClient(app).get("/runtime/projections/drift")

    assert response.status_code == 200
    body = response.json()
    assert body["projection_count"] == 11
    assert [
        result["projection_name"] for result in body["projections"]
    ] == [
        "artifact_lineage_projection",
        "decision_lineage_projection",
        "decision_projection",
        "evaluation_outcome_rollup",
        "evaluation_summary",
        "evaluation_trend",
        "governance_audit_projection",
        "policy_evaluation_overview",
        "policy_evidence",
        "policy_summary",
        "session_decision_projection",
    ]
