from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.governance_audit import GovernanceAuditSummary
from app.models.runtime_event import EventType, RuntimeEvent
from app.models.runtime_reconstruction import RuntimeReconstructionMetrics
from app.services.event_service import EventService
from app.services.operational_analytics_service import (
    OperationalAnalyticsGenerationError,
    OperationalAnalyticsService,
)
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class StaticSessions:
    def __init__(self, statuses):
        self.statuses = statuses

    def list_sessions(self):
        return [
            SimpleNamespace(id=f"session-{index}", status=status)
            for index, status in enumerate(self.statuses, start=1)
        ]


class StaticGovernance:
    def __init__(self, summary):
        self._summary = summary

    def summary(self):
        return self._summary


class StaticProjections:
    def __init__(self, projection_types=None, exc=None):
        self._projection_types = projection_types or [
            "artifact_lineage",
            "decision_lineage",
            "governance_audit",
        ]
        self._exc = exc

    def list_projection_types(self):
        if self._exc is not None:
            raise self._exc
        return list(self._projection_types)


class StaticReconstruction:
    def __init__(self, metrics=None):
        self._metrics = metrics or RuntimeReconstructionMetrics(
            reconstruction_views_built_total=2,
            reconstruction_incomplete_views_total=1,
            reconstruction_failed_views_total=1,
            reconstructed_sessions_total=2,
        )

    def metrics(self):
        return self._metrics


def append_event(
    trace: TraceService,
    event_id: int,
    event_type: EventType,
    day: str,
    metadata: dict | None = None,
) -> None:
    trace.append_event(
        RuntimeEvent(
            id=event_id,
            ts=f"{day}T10:00:00+00:00",
            type=event_type,
            message=event_type.value,
            metadata=metadata or {},
        )
    )


def make_service(tmp_path, **overrides):
    trace = TraceService(tmp_path / "analytics.db")
    events = EventService(trace)
    event_rows = [
        (1, EventType.PROPOSAL_GENERATED, "2026-06-13", {}),
        (2, EventType.PROPOSAL_RESOLVED, "2026-06-13", {}),
        (3, EventType.DECISION_RECORD_CREATED, "2026-06-14", {}),
        (4, EventType.ARTIFACT_CREATED, "2026-06-14", {}),
        (5, EventType.TOOL_EXECUTION_COMPLETED, "2026-06-14", {}),
        (6, EventType.TOOL_EXECUTION_FAILED, "2026-06-14", {}),
        (7, EventType.PROJECTION_REBUILD_COMPLETED, "2026-06-15", {}),
        (8, EventType.PROJECTION_REPLAY_COMPLETED, "2026-06-15", {}),
        (9, EventType.PROJECTION_DRIFT_CHECK_COMPLETED, "2026-06-15", {}),
        (10, EventType.PROJECTION_DRIFT_DETECTED, "2026-06-15", {}),
        (11, EventType.PROJECTION_REBUILD_FAILED, "2026-06-15", {}),
        (
            12,
            EventType.RUNTIME_RECONSTRUCTION_VIEW_BUILT,
            "2026-06-15",
            {"duration_ms": 20.0, "reconstructed_session_id": "session-1"},
        ),
        (
            13,
            EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE,
            "2026-06-15",
            {"duration_ms": 40.0, "reconstructed_session_id": "session-2"},
        ),
    ]
    for event_id, event_type, day, metadata in event_rows:
        append_event(trace, event_id, event_type, day, metadata)

    service = OperationalAnalyticsService(
        events=events,
        sessions=overrides.get(
            "sessions",
            StaticSessions(
                ["created", "running", "completed", "interrupted", "stopped"]
            ),
        ),
        governance=overrides.get(
            "governance",
            StaticGovernance(
                GovernanceAuditSummary(
                    governance_records_total=5,
                    approvals_total=2,
                    rejections_total=1,
                    policy_evaluations_total=1,
                    reflection_triggers_total=1,
                    budget_actions_total=1,
                    total_decisions=3,
                    approvals=2,
                    rejections=1,
                    policy_evaluations=1,
                    reflection_triggers=1,
                    budget_actions=1,
                    last_governance_activity_timestamp=GENERATED_AT,
                )
            ),
        ),
        projections=overrides.get("projections", StaticProjections()),
        reconstruction=overrides.get("reconstruction", StaticReconstruction()),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.025, 2.0, 2.025, 3.0, 3.025]).__next__,
    )
    return service, events


def without_generated_at(value: dict) -> dict:
    value = dict(value)
    value.pop("generated_at", None)
    return value


def test_operational_analytics_aggregation(tmp_path) -> None:
    service, events = make_service(tmp_path)

    analytics = service.generate(lookback_days=3)

    assert analytics.total_sessions == 5
    assert analytics.active_sessions == 2
    assert analytics.completed_sessions == 1
    assert analytics.failed_sessions == 2
    assert analytics.total_events == 13
    assert analytics.total_proposals == 1
    assert analytics.total_decisions == 1
    assert analytics.total_artifacts == 1
    assert analytics.total_tool_executions == 2
    assert analytics.metadata["authoritative_source"] == "runtime_event_store"
    generated = events.list_persisted_events(
        event_type="operational_analytics_generated"
    )
    assert generated[-1].metadata["analytics_requests_total"] == 1
    assert generated[-1].metadata["analytics_generation_duration_ms"] == 25.0


def test_governance_projection_and_reconstruction_aggregation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    analytics = service.generate()

    assert analytics.governance.model_dump() == {
        "approvals": 2,
        "rejections": 1,
        "policy_evaluations": 1,
        "reflection_triggers": 1,
        "budget_actions": 1,
        "governance_activity_rate": 1.2,
    }
    assert analytics.projections.model_dump() == {
        "registered_projections": 3,
        "projection_rebuilds": 1,
        "projection_replays": 1,
        "drift_checks": 2,
        "drift_detections": 1,
        "projection_failures": 1,
    }
    assert analytics.reconstruction.model_dump() == {
        "reconstructed_sessions": 2,
        "reconstruction_failures": 1,
        "incomplete_reconstructions": 1,
        "average_reconstruction_duration_ms": 30.0,
    }


def test_trend_generation_has_deterministic_ordering(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    first = service.trends(lookback_days=3)
    second = service.trends(lookback_days=3)

    assert first == second
    assert [bucket.day.isoformat() for bucket in first.buckets] == [
        "2026-06-13",
        "2026-06-14",
        "2026-06-15",
    ]
    assert first.events_per_day == {
        "2026-06-13": 2,
        "2026-06-14": 4,
        "2026-06-15": 7,
    }
    assert first.decisions_per_day["2026-06-14"] == 1
    assert first.artifacts_per_day["2026-06-14"] == 1
    assert first.governance_actions_per_day["2026-06-13"] == 1


def test_empty_event_store_generates_zero_analytics(tmp_path) -> None:
    trace = TraceService(tmp_path / "empty-analytics.db")
    service = OperationalAnalyticsService(
        events=EventService(trace),
        sessions=StaticSessions([]),
        governance=StaticGovernance(
            GovernanceAuditSummary(
                governance_records_total=0,
                approvals_total=0,
                rejections_total=0,
                policy_evaluations_total=0,
                reflection_triggers_total=0,
                budget_actions_total=0,
                total_decisions=0,
                approvals=0,
                rejections=0,
                policy_evaluations=0,
                reflection_triggers=0,
                budget_actions=0,
            )
        ),
        projections=StaticProjections(projection_types=[]),
        reconstruction=StaticReconstruction(
            RuntimeReconstructionMetrics(
                reconstruction_views_built_total=0,
                reconstruction_incomplete_views_total=0,
                reconstruction_failed_views_total=0,
                reconstructed_sessions_total=0,
            )
        ),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.0]).__next__,
    )

    analytics = service.generate(lookback_days=2)

    assert analytics.total_events == 0
    assert analytics.total_sessions == 0
    assert analytics.governance.governance_activity_rate == 0
    assert analytics.trends.events_per_day == {
        "2026-06-14": 0,
        "2026-06-15": 0,
    }


def test_malformed_event_timestamp_is_ignored_for_trends(tmp_path) -> None:
    trace = TraceService(tmp_path / "malformed-trends.db")
    append_event(trace, 1, EventType.DECISION_RECORD_CREATED, "2026-06-15")
    trace.append_event(
        RuntimeEvent(
            id=2,
            ts="not-a-timestamp",
            type=EventType.ARTIFACT_CREATED,
            message="Malformed timestamp",
        )
    )
    service = OperationalAnalyticsService(
        events=EventService(trace),
        sessions=StaticSessions([]),
        governance=StaticGovernance(
            GovernanceAuditSummary(
                governance_records_total=0,
                approvals_total=0,
                rejections_total=0,
                policy_evaluations_total=0,
                reflection_triggers_total=0,
                budget_actions_total=0,
                total_decisions=0,
                approvals=0,
                rejections=0,
                policy_evaluations=0,
                reflection_triggers=0,
                budget_actions=0,
            )
        ),
        projections=StaticProjections(projection_types=[]),
        reconstruction=StaticReconstruction(
            RuntimeReconstructionMetrics(
                reconstruction_views_built_total=0,
                reconstruction_incomplete_views_total=0,
                reconstruction_failed_views_total=0,
                reconstructed_sessions_total=0,
            )
        ),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.0]).__next__,
    )

    trends = service.trends(lookback_days=1)

    assert trends.events_per_day == {"2026-06-15": 1}
    assert trends.artifacts_per_day == {"2026-06-15": 0}


def test_missing_source_projections_yield_partial_analytics(tmp_path) -> None:
    service, _ = make_service(
        tmp_path,
        projections=StaticProjections(exc=LookupError("registry unavailable")),
    )

    analytics = service.generate()

    assert analytics.incomplete is True
    assert analytics.incomplete_reasons == ["projection_analytics_unavailable"]
    assert analytics.projections.registered_projections == 0
    assert analytics.total_events == 13


def test_partial_analytics_generation_preserves_available_sections(
    tmp_path,
) -> None:
    service, _ = make_service(
        tmp_path,
        governance=StaticGovernance({"malformed": True}),
    )

    analytics = service.generate()

    assert analytics.incomplete is True
    assert analytics.incomplete_reasons == ["governance_analytics_unavailable"]
    assert analytics.governance.approvals == 0
    assert analytics.projections.registered_projections == 3
    assert analytics.reconstruction.reconstructed_sessions == 2


def test_malformed_analytics_inputs_emit_failure(tmp_path) -> None:
    service, events = make_service(
        tmp_path,
        governance=StaticGovernance({"malformed": True}),
    )

    with pytest.raises(OperationalAnalyticsGenerationError):
        service.governance()

    failed = events.list_persisted_events(
        event_type="operational_analytics_failed"
    )
    assert failed[-1].metadata["error_type"] == "TypeError"
    assert failed[-1].metadata["analytics_generation_failures_total"] == 1


def test_operational_analytics_routes() -> None:
    client = TestClient(app)

    full = client.get("/runtime/analytics")
    governance = client.get("/runtime/analytics/governance")
    projections = client.get("/runtime/analytics/projections")
    reconstruction = client.get("/runtime/analytics/reconstruction")
    trends = client.get("/runtime/analytics/trends", params={"lookback_days": 2})

    assert full.status_code == 200
    assert governance.status_code == 200
    assert projections.status_code == 200
    assert reconstruction.status_code == 200
    assert trends.status_code == 200
    assert "governance" in full.json()
    assert "governance_activity_rate" in governance.json()
    assert "registered_projections" in projections.json()
    assert "average_reconstruction_duration_ms" in reconstruction.json()
    assert trends.json()["lookback_days"] == 2
