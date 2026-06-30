from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.services.event_service import event_service
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


NOW = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def seed_session(tmp_path):
    runtime_session_service.set_db_path(tmp_path / "sessions.db")
    event_service.set_trace_store(TraceService(tmp_path / "events.db"))

    session = runtime_session_service.create_session("task-1")
    runtime_session_service.mark_running(session.id)
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_STARTED,
        "Agent loop started",
        metadata={
            "session_id": session.id,
            "user_request": "Explain the current state",
            "provider_id": "mock",
            "model": "mock-small",
            "max_iterations": 3,
        },
    )
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_TOOL_SELECTED,
        "Tool selected",
        metadata={
            "session_id": session.id,
            "iteration": 1,
            "tool": "final_answer",
        },
    )
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_APPROVAL_REQUESTED,
        "Approval requested",
        metadata={
            "session_id": session.id,
            "approval_id": "approval-1",
            "iteration": 1,
            "tool": "shell",
        },
    )
    return session


def test_runtime_session_overview(tmp_path) -> None:
    session = seed_session(tmp_path)
    client = TestClient(app)

    response = client.get(f"/runtime/session/{session.id}")
    summary_response = client.get(f"/runtime/session/{session.id}/summary")

    assert response.status_code == 200
    assert summary_response.status_code == 200
    body = response.json()
    assert summary_response.json() == body
    assert body == {
        "session_id": session.id,
        "status": "running",
        "user_request": "Explain the current state",
        "workspace_id": None,
        "workspace_root_path": None,
        "provider": "mock",
        "model": "mock-small",
        "current_iteration": 1,
        "max_iterations": 3,
        "pending_approval": True,
        "pending_approval_id": "approval-1",
        "last_tool": "shell",
        "final_answer": None,
        "error": None,
        "started_at": session.created_at.isoformat(),
        "updated_at": session.created_at.isoformat(),
    }


def test_runtime_session_overview_404(tmp_path) -> None:
    runtime_session_service.set_db_path(tmp_path / "sessions.db")
    event_service.set_trace_store(TraceService(tmp_path / "events.db"))
    client = TestClient(app)

    response = client.get("/runtime/session/missing")
    summary_response = client.get("/runtime/session/missing/summary")

    assert response.status_code == 404
    assert summary_response.status_code == 404


def test_runtime_session_governance_snapshot(tmp_path) -> None:
    session = seed_session(tmp_path)
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        "Approval responded",
        metadata={
            "session_id": session.id,
            "approval_id": "approval-1",
            "status": "approved",
            "reason": "Looks good",
        },
    )
    event_service.emit_event_sync(
        EventType.RUNTIME_SESSION_INTERRUPTED,
        "Session interrupted",
        metadata={
            "session_id": session.id,
            "reason": "operator requested pause",
        },
    )

    client = TestClient(app)
    response = client.get(f"/runtime/session/{session.id}/governance")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.id
    assert body["pending_approval"] is False
    assert body["pending_approval_id"] == "approval-1"
    assert body["interrupted"] is True
    assert body["interrupt_reason"] == "operator requested pause"
    assert body["approval_history"][0]["approval_id"] == "approval-1"
    assert body["approval_history"][1]["status"] == "approved"
