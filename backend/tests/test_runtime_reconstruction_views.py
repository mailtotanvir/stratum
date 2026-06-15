from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.models.artifact_lineage import ArtifactLineageRecord
from app.models.decision_lineage import DecisionLineageRecord
from app.models.governance_audit import GovernanceAuditRecord
from app.models.runtime_event import EventType, Severity
from app.models.runtime_health import RuntimeHealthStatus
from app.services.event_service import EventService, event_service
from app.services.runtime_reconstruction_service import (
    RuntimeReconstructionService,
)
from app.services.runtime_session_service import RuntimeSessionService
from app.services.trace_service import TraceService


NOW = datetime(2026, 6, 15, 18, 0, tzinfo=UTC)


class StaticHealth:
    def evaluate(self) -> RuntimeHealthStatus:
        return RuntimeHealthStatus(
            overall_status="healthy",
            generated_at=NOW,
            health_score=96,
            subsystem_results=[],
            findings=[],
            diagnostics={},
        )


def make_service(tmp_path, *, decisions=None, artifacts=None):
    events = EventService(TraceService(tmp_path / "reconstruction.db"))
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    session = sessions.create_session("task-1")
    session = sessions.mark_running(session.id)
    service = RuntimeReconstructionService(
        events=events,
        sessions=sessions,
        decisions=SimpleNamespace(
            list_records=lambda: list(decisions or [])
        ),
        artifacts=SimpleNamespace(
            list_records=lambda: list(artifacts or [])
        ),
        governance=SimpleNamespace(list_records=lambda: []),
        health=StaticHealth(),
    )
    return service, events, session


def emit_session_events(events: EventService, session_id: str) -> None:
    events.emit_event_sync(
        EventType.RUNTIME_SESSION_CREATED,
        "Session created",
        metadata={
            "runtime_session_id": session_id,
            "task_id": "task-1",
            "status": "created",
        },
    )
    events.emit_event_sync(
        EventType.RUNTIME_SESSION_RUNNING,
        "Session running",
        metadata={
            "runtime_session_id": session_id,
            "task_id": "task-1",
            "status": "running",
        },
    )
    events.emit_event_sync(
        EventType.TOOL_EXECUTION_STARTED,
        "Tool started",
        metadata={
            "session_id": session_id,
            "tool_invocation_id": "invocation-1",
            "tool_id": "tool-1",
            "tool_name": "build",
        },
    )
    events.emit_event_sync(
        EventType.TOOL_EXECUTION_COMPLETED,
        "Tool completed",
        metadata={
            "session_id": session_id,
            "tool_invocation_id": "invocation-1",
            "tool_id": "tool-1",
            "tool_name": "build",
            "output_payload": {"artifacts": ["artifact-1"]},
        },
    )


def decision_record(session_id: str) -> DecisionLineageRecord:
    return DecisionLineageRecord(
        decision_id="decision-1",
        session_id=session_id,
        recommendation_id="recommendation-1",
        proposal_id="proposal-1",
        parent_decision_id=None,
        lineage_depth=0,
        selected_at=NOW,
        decision_type="recommendation_selection",
        outcome="approved",
        evidence_count=1,
        source_event_ids=[1],
        related_artifact_ids=["artifact-1"],
        related_proposal_ids=["proposal-1"],
        metadata={"orphaned": False},
    )


def artifact_record(session_id: str) -> ArtifactLineageRecord:
    return ArtifactLineageRecord(
        artifact_id="artifact-1",
        artifact_path="reports/result.md",
        artifact_type="report",
        session_id=session_id,
        source_event_id=1,
        producing_tool_invocation_id="invocation-1",
        proposal_id="proposal-1",
        decision_id="decision-1",
        parent_artifact_ids=[],
        related_event_ids=[1],
        created_at=NOW,
        updated_at=NOW,
        lineage_status="linked",
        metadata={},
    )


def test_session_list_reconstruction(tmp_path) -> None:
    service, events, session = make_service(tmp_path)
    emit_session_events(events, session.id)

    summaries = service.list_sessions()

    assert len(summaries) == 1
    assert summaries[0].session_id == session.id
    assert summaries[0].event_count == 4
    assert summaries[0].health_status == "healthy"


def test_full_reconstruction_includes_health_and_lineage(tmp_path) -> None:
    service, events, session = make_service(tmp_path)
    service._decisions = SimpleNamespace(
        list_records=lambda: [decision_record(session.id)]
    )
    service._artifacts = SimpleNamespace(
        list_records=lambda: [artifact_record(session.id)]
    )
    service._governance = SimpleNamespace(
        list_records=lambda: [
            GovernanceAuditRecord(
                decision_id="governance-1",
                decision_type="policy_evaluation",
                session_id=session.id,
                source_event_id=1,
                occurred_at=NOW,
                actor="runtime",
                outcome="allow",
                evidence_count=0,
                metadata={},
            )
        ]
    )
    emit_session_events(events, session.id)
    events.emit_event_sync(
        EventType.PROPOSAL_GENERATED,
        "Proposal generated",
        metadata={
            "proposal_id": "proposal-1",
            "task_id": "task-1",
            "source_type": "planner_recommendation",
            "source_id": "recommendation-1",
            "status": "proposed",
            "title": "Apply recommendation",
        },
    )

    view = service.reconstruct(session.id)

    assert view.session_id == session.id
    assert view.total_events == 5
    assert view.health_consistency_status.status == "healthy"
    assert view.health_consistency_status.health_score == 96
    assert view.decision_lineage_summaries[0].decision_id == "decision-1"
    assert view.artifact_lineage_summaries[0].artifact_id == "artifact-1"
    assert view.tool_execution_summaries[0].artifact_ids == ["artifact-1"]
    assert view.governance_decisions[0].decision_id == "governance-1"
    assert view.proposal_summaries[0].proposal_id == "proposal-1"
    assert view.incomplete is False


def test_timeline_ordering_is_deterministic(tmp_path) -> None:
    service, events, session = make_service(tmp_path)
    emit_session_events(events, session.id)

    first = service.timeline(session.id)
    second = service.timeline(session.id)

    assert first == second
    assert [item.event_id for item in first] == [1, 2, 3, 4]


def test_incomplete_projection_tolerance(tmp_path) -> None:
    service, events, session = make_service(tmp_path)
    service._decisions = SimpleNamespace(
        list_records=lambda: [{"malformed": True}]
    )
    service._artifacts = SimpleNamespace(
        list_records=lambda: (_ for _ in ()).throw(
            ValueError("projection unavailable")
        )
    )
    emit_session_events(events, session.id)

    view = service.reconstruct(session.id)

    assert view.incomplete is True
    assert view.incomplete_reasons == [
        "artifact_lineage_unavailable",
        "malformed_decision_lineage_data",
    ]
    assert view.health_consistency_status.consistency_status == "incomplete"
    assert events.list_persisted_events(
        event_type="runtime_reconstruction_view_incomplete"
    )


def test_reconstruction_diagnostics_do_not_change_session_output(
    tmp_path,
) -> None:
    service, events, session = make_service(tmp_path)
    emit_session_events(events, session.id)

    first = service.reconstruct(session.id)
    second = service.reconstruct(session.id)

    assert first == second
    assert first.total_events == second.total_events == 4
    assert service.metrics().model_dump() == {
        "reconstruction_views_built_total": 2,
        "reconstruction_incomplete_views_total": 0,
        "reconstruction_failed_views_total": 0,
        "reconstructed_sessions_total": 1,
    }


def test_missing_session_emits_failed_diagnostic(tmp_path) -> None:
    service, events, _ = make_service(tmp_path)

    try:
        service.reconstruct("missing-session")
    except Exception as exc:
        assert str(exc) == "Runtime session not found: missing-session"
    else:
        raise AssertionError("missing session must fail")

    assert len(
        events.list_persisted_events(
            event_type="runtime_reconstruction_view_failed"
        )
    ) == 1


def test_reconstruction_routes() -> None:
    client = TestClient(app)
    client.post("/runtime/tasks/task-reconstruction/run")
    session_id = client.get(
        "/runtime/sessions",
        params={"task_id": "task-reconstruction"},
    ).json()[0]["id"]

    listing = client.get("/runtime/reconstruction/sessions")
    detail = client.get(
        f"/runtime/reconstruction/sessions/{session_id}"
    )
    timeline = client.get(
        f"/runtime/reconstruction/sessions/{session_id}/timeline"
    )

    assert listing.status_code == 200
    assert listing.json()[0]["session_id"] == session_id
    assert detail.status_code == 200
    assert detail.json()["session_id"] == session_id
    assert timeline.status_code == 200
    assert [
        item["event_id"] for item in timeline.json()
    ] == sorted(item["event_id"] for item in timeline.json())


def test_missing_session_route_returns_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/reconstruction/sessions/missing-session"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Runtime session not found: missing-session"
    }
