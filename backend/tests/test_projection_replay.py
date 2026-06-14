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
from app.services.projection_replay_service import (
    EventTypeProjectionReplayAdapter,
    ProjectionReplayError,
    ProjectionReplayService,
)
from app.services.trace_service import TraceService


STARTED_AT = datetime(2026, 6, 14, 14, 0, tzinfo=UTC)


class ReplayProjectionBuilder:
    projection_type = "replay_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=2,
        builder_name="ReplayProjectionBuilder",
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
        raise AssertionError("projection replay must not invoke builders")


class FailingReplayAdapter:
    def accepts(self, event) -> bool:
        return True

    def apply(self, state, event) -> None:
        raise RuntimeError(f"cannot apply event {event.id}")


def make_replay_service(
    tmp_path,
    *,
    adapter=None,
    clock_values=None,
):
    builder = ReplayProjectionBuilder()
    registry = ProjectionRegistry()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_replay.db"))
    service = ProjectionReplayService(
        registry=registry,
        events=events,
        adapters={
            "replay_projection": adapter
            or EventTypeProjectionReplayAdapter(
                frozenset(
                    {
                        EventType.DECISION_RECORD_CREATED,
                        EventType.DECISION_EVIDENCE_CREATED,
                    }
                )
            )
        },
        clock=lambda: next(clock_values),
    )
    return service, events, builder


def emit_source_events(events: EventService) -> None:
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Decision one",
    )
    events.emit_event_sync(EventType.WARNING, "Unrelated warning")
    events.emit_event_sync(
        EventType.DECISION_EVIDENCE_CREATED,
        "Evidence one",
    )


def test_projection_replay_full_event_store(tmp_path) -> None:
    completed_at = STARTED_AT + timedelta(milliseconds=25)
    service, events, builder = make_replay_service(
        tmp_path,
        clock_values=iter([STARTED_AT, completed_at]),
    )
    emit_source_events(events)

    result = service.replay(
        ProjectionReplayRequest(projection_name="replay_projection")
    )

    assert result.model_dump() == {
        "projection_name": "replay_projection",
        "projection_version": 2,
        "replay_started_at": STARTED_AT,
        "replay_completed_at": completed_at,
        "status": "completed",
        "source_event_count": 3,
        "applied_event_count": 2,
        "skipped_event_count": 1,
        "failed_event_count": 0,
        "duration_ms": 25.0,
        "dry_run": False,
    }
    assert builder.build_calls == []
    completed = events.list_persisted_events(
        event_type="projection_replay_completed"
    )
    assert completed[-1].metadata["applied_event_count"] == 2


def test_projection_replay_supports_bounded_event_range(tmp_path) -> None:
    service, events, _ = make_replay_service(
        tmp_path,
        clock_values=iter(
            [STARTED_AT, STARTED_AT + timedelta(milliseconds=10)]
        ),
    )
    emit_source_events(events)

    result = service.replay(
        ProjectionReplayRequest(
            projection_name="replay_projection",
            event_id_start=2,
            event_id_end=3,
        )
    )

    assert result.source_event_count == 2
    assert result.applied_event_count == 1
    assert result.skipped_event_count == 1


def test_projection_replay_dry_run_does_not_build_or_retain_state(
    tmp_path,
) -> None:
    service, events, builder = make_replay_service(
        tmp_path,
        clock_values=iter(
            [
                STARTED_AT,
                STARTED_AT + timedelta(milliseconds=5),
                STARTED_AT + timedelta(seconds=1),
                STARTED_AT
                + timedelta(seconds=1, milliseconds=5),
            ]
        ),
    )
    emit_source_events(events)

    first = service.preview(
        ProjectionReplayRequest(projection_name="replay_projection")
    )
    second = service.preview(
        ProjectionReplayRequest(projection_name="replay_projection")
    )

    assert first.applied_event_count == second.applied_event_count == 2
    assert first.skipped_event_count == second.skipped_event_count == 1
    assert builder.build_calls == []
    assert len(
        events.list_persisted_events(
            event_type="projection_replay_dry_run_completed"
        )
    ) == 2


def test_projection_replay_failure_is_isolated_and_reported(tmp_path) -> None:
    service, events, builder = make_replay_service(
        tmp_path,
        adapter=FailingReplayAdapter(),
        clock_values=iter(
            [STARTED_AT, STARTED_AT + timedelta(milliseconds=7)]
        ),
    )
    emit_source_events(events)

    with pytest.raises(
        ProjectionReplayError,
        match="cannot apply event 1",
    ) as exc_info:
        service.replay(
            ProjectionReplayRequest(
                projection_name="replay_projection"
            )
        )

    result = exc_info.value.result
    assert result.status == "failed"
    assert result.applied_event_count == 0
    assert result.failed_event_count == 1
    assert builder.build_calls == []
    failed = events.list_persisted_events(
        event_type="projection_replay_failed"
    )
    assert failed[-1].severity.value == "error"
    assert failed[-1].metadata["failed_event_count"] == 1


def test_projection_replay_event_order_is_deterministic(tmp_path) -> None:
    applied_ids: list[int] = []

    class RecordingAdapter:
        def accepts(self, event) -> bool:
            return True

        def apply(self, state, event) -> None:
            applied_ids.append(event.id)

    service, events, _ = make_replay_service(
        tmp_path,
        adapter=RecordingAdapter(),
        clock_values=iter(
            [STARTED_AT, STARTED_AT + timedelta(milliseconds=1)]
        ),
    )
    emit_source_events(events)

    service.replay(
        ProjectionReplayRequest(projection_name="replay_projection")
    )

    assert applied_ids == [1, 2, 3]


def test_projection_replay_routes() -> None:
    client = TestClient(app)

    preview = client.get(
        "/runtime/projections/replay/preview",
        params={"projection_name": "decision_projection"},
    )
    replay = client.post(
        "/runtime/projections/replay",
        json={"projection_name": "decision_projection"},
    )

    assert preview.status_code == 200
    assert preview.json()["projection_name"] == "decision_projection"
    assert preview.json()["dry_run"] is True
    assert replay.status_code == 200
    assert replay.json()["projection_name"] == "decision_projection"
    assert replay.json()["dry_run"] is False


def test_projection_replay_route_returns_unknown_projection() -> None:
    response = TestClient(app).post(
        "/runtime/projections/replay",
        json={"projection_name": "missing_projection"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }


def test_projection_replay_preview_validates_event_range() -> None:
    response = TestClient(app).get(
        "/runtime/projections/replay/preview",
        params={
            "projection_name": "decision_projection",
            "event_id_start": 10,
            "event_id_end": 5,
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "event_id_start must be less than or equal to event_id_end"
        )
    }
