from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.services.event_service import EventService
from app.services.runtime_dashboard_service import (
    RuntimeDashboardGenerationError,
    RuntimeDashboardService,
)
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 13, 20, 0, tzinfo=UTC)


class StaticService:
    def __init__(self, records):
        self.records = records

    def list_sessions(self):
        return list(self.records)

    def list_decision_records(self):
        return list(self.records)

    def list_recommendations(self):
        return list(self.records)

    def list_proposals(self):
        return list(self.records)


class StaticDiagnostics:
    def governance_health(self):
        return {
            "status": "degraded",
            "highest_severity": "warning",
            "has_critical": False,
            "error_budget": {"status": "within_budget"},
        }


class StaticHealth:
    def evaluate(self):
        return SimpleNamespace(
            overall_status="warning",
            health_score=82,
            subsystem_results=[
                SimpleNamespace(
                    subsystem_name="runtime",
                    status="healthy",
                    score=100,
                ),
                SimpleNamespace(
                    subsystem_name="queries",
                    status="degraded",
                    score=64,
                ),
            ],
        )


def make_dashboard_service(tmp_path):
    events = EventService(TraceService(tmp_path / "dashboard.db"))
    sessions = [
        SimpleNamespace(status="created"),
        SimpleNamespace(status="running"),
        SimpleNamespace(status="completed"),
        SimpleNamespace(status="interrupted"),
        SimpleNamespace(status="stopped"),
    ]
    decisions = [
        SimpleNamespace(selected_entity_id="recommendation-1"),
        SimpleNamespace(selected_entity_id="recommendation-1"),
        SimpleNamespace(selected_entity_id="recommendation-2"),
    ]
    recommendations = [
        SimpleNamespace(status="active"),
        SimpleNamespace(status="promoted"),
        SimpleNamespace(status="dismissed"),
    ]
    proposals = [
        SimpleNamespace(status="proposed"),
        SimpleNamespace(status="approved"),
        SimpleNamespace(status="approved"),
        SimpleNamespace(status="rejected"),
    ]
    timer_values = iter([1.0, 1.025, 2.0, 2.025])
    service = RuntimeDashboardService(
        events=events,
        sessions=StaticService(sessions),
        decisions=StaticService(decisions),
        recommendations=StaticService(recommendations),
        proposals=StaticService(proposals),
        projections=SimpleNamespace(
            list_projection_types=lambda: [
                "decision_projection",
                "session_decision_projection",
            ]
        ),
        queries=SimpleNamespace(
            list_query_names=lambda: ["session_decision_summary"]
        ),
        diagnostics=StaticDiagnostics(),
        clock=lambda: GENERATED_AT,
        timer=lambda: next(timer_values),
        runtime_version="0.6.0",
        health=StaticHealth(),
    )
    return service, events


def emit_dashboard_events(events: EventService) -> None:
    for event_type in [
        EventType.PROJECTION_REBUILD_COMPLETED,
        EventType.PROJECTION_REBUILD_COMPLETED,
        EventType.PROJECTION_VERIFICATION_COMPLETED,
        EventType.RUNTIME_QUERY_EXECUTION_COMPLETED,
        EventType.RUNTIME_QUERY_EXECUTION_COMPLETED,
        EventType.QUERY_VERIFICATION_COMPLETED,
    ]:
        events.emit_event_sync(event_type, event_type.value)
    events.emit_event_sync(
        EventType.RUNTIME_GOVERNANCE_WARNING,
        "Governance warning",
        severity="warning",
    )
    events.emit_event_sync(
        EventType.ERROR,
        "Runtime error",
        severity="error",
    )


def test_runtime_dashboard_generation_is_versioned_and_deterministic(
    tmp_path,
) -> None:
    service, events = make_dashboard_service(tmp_path)
    emit_dashboard_events(events)

    first = service.generate()
    second = service.generate()

    assert first == second
    assert first.generated_at == GENERATED_AT
    sections = [
        first.runtime_summary,
        first.session_summary,
        first.decision_summary,
        first.projection_summary,
        first.query_summary,
        first.governance_summary,
        first.diagnostics_summary,
        first.health_summary,
    ]
    assert len(sections) == 8
    assert all(section.section_version == 1 for section in sections)
    assert all(section.generated_at == GENERATED_AT for section in sections)
    assert all(section.metadata["derived"] is True for section in sections)
    generated = events.list_persisted_events(
        event_type="runtime_dashboard_generated"
    )
    assert len(generated) == 2
    assert generated[0].metadata == {
        "generation_duration_ms": 25.0,
        "section_count": 8,
    }


def test_runtime_dashboard_runtime_and_session_summaries(tmp_path) -> None:
    service, events = make_dashboard_service(tmp_path)
    emit_dashboard_events(events)

    dashboard = service.generate()

    assert dashboard.runtime_summary.summary == {
        "runtime_version": "0.6.0",
        "active_sessions": 2,
        "completed_sessions": 1,
        "session_counts": {
            "created": 1,
            "running": 1,
            "completed": 1,
            "interrupted": 1,
            "stopped": 1,
        },
        "event_counts": {
            "error": 1,
            "projection_rebuild_completed": 2,
            "projection_verification_completed": 1,
            "query_verification_completed": 1,
            "runtime_governance_warning": 1,
            "runtime_query_execution_completed": 2,
        },
        "total_events": 8,
    }
    assert dashboard.session_summary.summary == {
        "total_sessions": 5,
        "active_sessions": 2,
        "completed_sessions": 1,
        "interrupted_sessions": 1,
        "stopped_sessions": 1,
        "status_counts": {
            "created": 1,
            "running": 1,
            "completed": 1,
            "interrupted": 1,
            "stopped": 1,
        },
    }


def test_runtime_dashboard_decision_summary(tmp_path) -> None:
    service, _ = make_dashboard_service(tmp_path)

    summary = service.generate().decision_summary.summary

    assert summary == {
        "decision_record_count": 3,
        "recommendation_count": 3,
        "selected_recommendation_count": 3,
        "recommendation_status_counts": {
            "active": 1,
            "promoted": 1,
            "dismissed": 1,
        },
    }


def test_runtime_dashboard_projection_and_query_summaries(tmp_path) -> None:
    service, events = make_dashboard_service(tmp_path)
    emit_dashboard_events(events)

    dashboard = service.generate()

    assert dashboard.projection_summary.summary == {
        "registered_projections": [
            "decision_projection",
            "session_decision_projection",
        ],
        "registered_projection_count": 2,
        "projection_rebuild_count": 2,
        "projection_verification_count": 1,
    }
    assert dashboard.query_summary.summary == {
        "registered_queries": ["session_decision_summary"],
        "registered_query_count": 1,
        "query_execution_count": 2,
        "query_verification_count": 1,
    }


def test_runtime_dashboard_governance_summary(tmp_path) -> None:
    service, events = make_dashboard_service(tmp_path)
    emit_dashboard_events(events)

    summary = service.generate().governance_summary.summary

    assert summary == {
        "proposal_count": 4,
        "approval_count": 2,
        "rejection_count": 1,
        "proposal_status_counts": {
            "proposed": 1,
            "approved": 2,
            "rejected": 1,
        },
        "governance_diagnostics": {
            "status": "degraded",
            "highest_severity": "warning",
            "has_critical": False,
            "error_budget_status": "within_budget",
            "event_count": 1,
        },
    }


def test_runtime_dashboard_diagnostics_summary(tmp_path) -> None:
    service, events = make_dashboard_service(tmp_path)
    emit_dashboard_events(events)

    summary = service.generate().diagnostics_summary.summary

    assert summary["warning_count"] == 1
    assert summary["error_count"] == 1
    assert summary["critical_count"] == 0
    assert len(summary["recent_diagnostic_events"]) == 8
    assert summary["recent_diagnostic_events"][-1]["event_type"] == "error"


def test_runtime_dashboard_includes_compact_health_summary(tmp_path) -> None:
    service, _ = make_dashboard_service(tmp_path)

    summary = service.generate().health_summary.summary

    assert summary == {
        "overall_status": "warning",
        "health_score": 82,
        "subsystems": [
            {
                "subsystem_name": "runtime",
                "status": "healthy",
                "score": 100,
            },
            {
                "subsystem_name": "queries",
                "status": "degraded",
                "score": 64,
            },
        ],
    }


def test_runtime_dashboard_failure_emits_diagnostic(tmp_path) -> None:
    events = EventService(TraceService(tmp_path / "failed_dashboard.db"))
    timer_values = iter([5.0, 5.01])
    service = RuntimeDashboardService(
        events=events,
        sessions=SimpleNamespace(
            list_sessions=lambda: (_ for _ in ()).throw(
                RuntimeError("sessions unavailable")
            )
        ),
        clock=lambda: GENERATED_AT,
        timer=lambda: next(timer_values),
        health=StaticHealth(),
    )

    with pytest.raises(
        RuntimeDashboardGenerationError,
        match="sessions unavailable",
    ):
        service.generate()

    failed = events.list_persisted_events(
        event_type="runtime_dashboard_generation_failed"
    )
    assert failed[-1].severity.value == "error"
    assert failed[-1].metadata == {
        "generation_duration_ms": 10.0,
        "section_count": 0,
    }


def test_runtime_dashboard_endpoint_is_operational() -> None:
    response = TestClient(app).get("/observability/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "generated_at",
        "runtime_summary",
        "session_summary",
        "decision_summary",
        "projection_summary",
        "query_summary",
        "governance_summary",
        "diagnostics_summary",
        "health_summary",
    }
    assert body["runtime_summary"]["summary"]["runtime_version"] == "0.6.0"
    assert body["projection_summary"]["summary"][
        "registered_projection_count"
    ] >= 1
    assert body["query_summary"]["summary"]["registered_query_count"] >= 1
    assert "overall_status" in body["health_summary"]["summary"]
    assert all(
        body[name]["metadata"]["derived"] is True
        for name in body
        if name != "generated_at"
    )
