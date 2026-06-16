from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.operational_analytics import (
    GovernanceAnalytics,
    ProjectionAnalytics,
    ReconstructionAnalytics,
    RuntimeOperationalAnalytics,
    RuntimeTrendAnalytics,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_health import RuntimeHealthFinding, RuntimeHealthStatus
from app.models.runtime_reconstruction import RuntimeReconstructionMetrics
from app.services.event_service import EventService
from app.services.runtime_intelligence_service import (
    RuntimeIntelligenceGenerationError,
    RuntimeIntelligenceService,
)
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class StaticAnalytics:
    def __init__(self, analytics=None, exc=None):
        self.analytics = analytics or make_analytics()
        self.exc = exc

    def generate(self):
        if self.exc is not None:
            raise self.exc
        return self.analytics


class StaticHealth:
    def __init__(self, status=None, exc=None):
        self.status = status or make_health()
        self.exc = exc

    def evaluate(self):
        if self.exc is not None:
            raise self.exc
        return self.status


class StaticLifecycle:
    def __init__(self, statuses=None, exc=None):
        self.statuses = statuses if statuses is not None else [
            SimpleNamespace(
                projection_name="fresh_projection",
                latest_rebuild_completed_at=GENERATED_AT - timedelta(days=1),
            ),
            SimpleNamespace(
                projection_name="stale_projection",
                latest_rebuild_completed_at=GENERATED_AT - timedelta(days=10),
            ),
            SimpleNamespace(
                projection_name="never_rebuilt_projection",
                latest_rebuild_completed_at=None,
            ),
        ]
        self.exc = exc

    def projection_statuses(self):
        if self.exc is not None:
            raise self.exc
        return list(self.statuses)


class StaticReconstruction:
    def __init__(self, metrics=None, exc=None):
        self.metrics_value = metrics or RuntimeReconstructionMetrics(
            reconstruction_views_built_total=2,
            reconstruction_incomplete_views_total=1,
            reconstruction_failed_views_total=1,
            reconstructed_sessions_total=2,
        )
        self.exc = exc

    def metrics(self):
        if self.exc is not None:
            raise self.exc
        return self.metrics_value


def make_analytics(
    *,
    approvals=1,
    rejections=4,
    drift_detections=1,
    projection_failures=2,
    reconstruction_failures=1,
    incomplete_reconstructions=1,
) -> RuntimeOperationalAnalytics:
    return RuntimeOperationalAnalytics(
        generated_at=GENERATED_AT,
        total_sessions=5,
        active_sessions=1,
        completed_sessions=3,
        failed_sessions=1,
        total_events=20,
        total_proposals=5,
        total_decisions=3,
        total_artifacts=2,
        total_tool_executions=4,
        governance=GovernanceAnalytics(
            approvals=approvals,
            rejections=rejections,
            policy_evaluations=2,
            reflection_triggers=1,
            budget_actions=1,
            governance_activity_rate=1.1,
        ),
        projections=ProjectionAnalytics(
            registered_projections=3,
            projection_rebuilds=4,
            projection_replays=2,
            drift_checks=2,
            drift_detections=drift_detections,
            projection_failures=projection_failures,
        ),
        reconstruction=ReconstructionAnalytics(
            reconstructed_sessions=2,
            reconstruction_failures=reconstruction_failures,
            incomplete_reconstructions=incomplete_reconstructions,
            average_reconstruction_duration_ms=25.0,
        ),
        trends=RuntimeTrendAnalytics(
            lookback_days=7,
            buckets=[],
            events_per_day={},
            decisions_per_day={},
            artifacts_per_day={},
            governance_actions_per_day={},
        ),
        metadata={"derived": True},
    )


def make_health(
    *,
    overall_status="degraded",
    critical=False,
) -> RuntimeHealthStatus:
    findings = (
        [
            RuntimeHealthFinding(
                finding_id="finding-critical",
                finding_type="diagnostic_critical",
                severity="critical",
                subsystem="diagnostics",
                summary="Critical diagnostic present",
            )
        ]
        if critical
        else []
    )
    return RuntimeHealthStatus(
        overall_status=overall_status,
        generated_at=GENERATED_AT,
        health_score=50,
        subsystem_results=[],
        findings=findings,
    )


def append_event(
    trace: TraceService,
    event_id: int,
    event_type: EventType,
    *,
    ts: str,
    severity: Severity = Severity.INFO,
    message: str | None = None,
) -> None:
    trace.append_event(
        RuntimeEvent(
            id=event_id,
            ts=ts,
            type=event_type,
            severity=severity,
            message=message or event_type.value,
            metadata={},
        )
    )


def make_service(tmp_path, **overrides):
    trace = TraceService(tmp_path / "intelligence.db")
    events = EventService(trace)
    append_event(
        trace,
        1,
        EventType.PROJECTION_REPLAY_FAILED,
        ts="2026-06-15T10:00:00+00:00",
        severity=Severity.ERROR,
    )
    append_event(
        trace,
        2,
        EventType.PROJECTION_REBUILD_FAILED,
        ts="2026-06-15T10:01:00+00:00",
        severity=Severity.ERROR,
    )
    append_event(
        trace,
        3,
        EventType.DECISION_LINEAGE_INCOMPLETE,
        ts="2026-06-15T10:02:00+00:00",
        severity=Severity.WARNING,
    )
    append_event(
        trace,
        4,
        EventType.PROJECTION_DRIFT_DETECTED,
        ts="2026-06-15T10:03:00+00:00",
        severity=Severity.WARNING,
    )
    append_event(
        trace,
        5,
        EventType.RUNTIME_GOVERNANCE_BLOCKED,
        ts="2026-06-15T10:04:00+00:00",
        severity=Severity.WARNING,
    )
    append_event(
        trace,
        6,
        EventType.ERROR,
        ts="2026-06-15T10:05:00+00:00",
        severity=Severity.CRITICAL,
        message="Critical runtime issue",
    )

    service = RuntimeIntelligenceService(
        events=events,
        analytics=overrides.get("analytics", StaticAnalytics()),
        health=overrides.get("health", StaticHealth(make_health(critical=True))),
        lifecycle=overrides.get("lifecycle", StaticLifecycle()),
        reconstruction=overrides.get("reconstruction", StaticReconstruction()),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.025, 2.0, 2.025, 3.0, 3.025]).__next__,
    )
    return service, events


def test_runtime_intelligence_summary_generation(tmp_path) -> None:
    service, events = make_service(tmp_path)

    summary = service.generate()

    assert summary.overall_status == "degraded"
    assert summary.health_status == "degraded"
    assert summary.projection_integrity_status == "degraded"
    assert summary.governance_status == "degraded"
    assert summary.reconstruction_status == "degraded"
    assert summary.risk_level == "critical"
    assert summary.recent_activity[0].event_type == "error"
    assert summary.metadata["authoritative_source"] == "runtime_event_store"
    generated = events.list_persisted_events(
        event_type="runtime_intelligence_generated"
    )
    assert generated[-1].metadata["intelligence_requests_total"] == 1
    assert generated[-1].metadata["runtime_risks_detected_total"] == 8


def test_risk_classification_and_deterministic_ordering(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    first = service.risks()
    second = service.risks()

    assert first == second
    assert first.risk_level == "critical"
    assert [risk.risk_id for risk in first.notable_risks] == [
        "critical_runtime_health",
        "governance_rejection_spike",
        "projection_drift_detected",
        "projection_rebuild_failures",
        "projection_replay_failures",
        "reconstruction_failures",
        "incomplete_lineage_or_reconstruction",
        "stale_projection_rebuilds",
    ]
    assert first.recommended_operator_attention == sorted(
        first.recommended_operator_attention
    )


def test_integrity_summary(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    integrity = service.integrity()

    assert integrity.projection_integrity_status == "degraded"
    assert integrity.reconstruction_status == "degraded"
    assert integrity.drift_detections == 1
    assert integrity.projection_failures == 2
    assert integrity.failed_rebuilds == 1
    assert integrity.failed_replays == 1
    assert integrity.stale_projection_rebuilds == 2
    assert integrity.incomplete_lineage_or_reconstructions == 3


def test_activity_summary(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    activity = service.activity()

    assert activity.high_signal_event_count == 6
    assert [item.event_id for item in activity.recent_activity] == [
        6,
        5,
        4,
        3,
        2,
        1,
    ]
    assert activity.recent_activity[1].signal == "governance"


def test_empty_event_store_generates_low_risk_intelligence(tmp_path) -> None:
    service = RuntimeIntelligenceService(
        events=EventService(TraceService(tmp_path / "empty-intelligence.db")),
        analytics=StaticAnalytics(
            make_analytics(
                approvals=0,
                rejections=0,
                drift_detections=0,
                projection_failures=0,
                reconstruction_failures=0,
                incomplete_reconstructions=0,
            )
        ),
        health=StaticHealth(make_health(overall_status="healthy")),
        lifecycle=StaticLifecycle(statuses=[]),
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

    summary = service.generate()

    assert summary.overall_status == "healthy"
    assert summary.risk_level == "low"
    assert summary.notable_risks == []
    assert summary.recent_activity == []


def test_malformed_activity_timestamp_is_ignored(tmp_path) -> None:
    trace = TraceService(tmp_path / "malformed-activity.db")
    trace.append_event(
        RuntimeEvent(
            id=1,
            ts="not-a-timestamp",
            type=EventType.PROJECTION_DRIFT_DETECTED,
            severity=Severity.WARNING,
            message="Malformed timestamp",
        )
    )
    append_event(
        trace,
        2,
        EventType.PROJECTION_REBUILD_FAILED,
        ts="2026-06-15T10:01:00+00:00",
        severity=Severity.ERROR,
    )
    service = RuntimeIntelligenceService(
        events=EventService(trace),
        analytics=StaticAnalytics(),
        health=StaticHealth(make_health(critical=True)),
        lifecycle=StaticLifecycle(),
        reconstruction=StaticReconstruction(),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.0]).__next__,
    )

    activity = service.activity()

    assert [item.event_id for item in activity.recent_activity] == [2]
    assert activity.high_signal_event_count == 1


def test_governance_intelligence_summary(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    governance = service.governance()

    assert governance.governance_status == "degraded"
    assert governance.rejection_rate == 0.8
    assert governance.rejection_spike_detected is True
    assert governance.recommended_operator_attention == [
        "review_governance_rejections"
    ]


def test_missing_analytics_data_fails_direct_risk_summary(tmp_path) -> None:
    service, events = make_service(
        tmp_path,
        analytics=StaticAnalytics(exc=RuntimeError("analytics unavailable")),
    )

    with pytest.raises(RuntimeIntelligenceGenerationError):
        service.risks()

    failed = events.list_persisted_events(
        event_type="runtime_intelligence_failed"
    )
    assert failed[-1].metadata["error_type"] == "RuntimeError"
    assert failed[-1].metadata["intelligence_generation_failures_total"] == 1


def test_missing_reconstruction_data_yields_partial_intelligence(
    tmp_path,
) -> None:
    service, _ = make_service(
        tmp_path,
        reconstruction=StaticReconstruction(exc=RuntimeError("missing")),
    )

    summary = service.generate()

    assert summary.incomplete is True
    assert summary.incomplete_reasons == ["reconstruction_data_unavailable"]
    assert summary.integrity_summary.reconstruction_failures == 1


def test_partial_intelligence_generation_when_analytics_unavailable(
    tmp_path,
) -> None:
    service, _ = make_service(
        tmp_path,
        analytics=StaticAnalytics(exc=RuntimeError("analytics unavailable")),
    )

    summary = service.generate()

    assert summary.incomplete is True
    assert summary.incomplete_reasons == ["operational_analytics_unavailable"]
    assert summary.risk_level == "critical"
    assert summary.notable_risks[0].risk_id == "critical_runtime_health"


def test_runtime_intelligence_routes() -> None:
    client = TestClient(app)

    full = client.get("/runtime/intelligence")
    risks = client.get("/runtime/intelligence/risks")
    activity = client.get("/runtime/intelligence/activity")
    integrity = client.get("/runtime/intelligence/integrity")

    assert full.status_code == 200
    assert risks.status_code == 200
    assert activity.status_code == 200
    assert integrity.status_code == 200
    assert "overall_status" in full.json()
    assert "notable_risks" in risks.json()
    assert "recent_activity" in activity.json()
    assert "projection_integrity_status" in integrity.json()
