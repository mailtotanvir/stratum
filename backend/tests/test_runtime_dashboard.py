from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.services.event_service import event_service
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


def seed_sessions(tmp_path) -> None:
    runtime_session_service.set_db_path(tmp_path / "sessions.db")
    event_service.set_trace_store(TraceService(tmp_path / "events.db"))

    created = runtime_session_service.create_session("task-created")
    running = runtime_session_service.create_session("task-running")
    runtime_session_service.mark_running(running.id)
    completed = runtime_session_service.create_session("task-completed")
    interrupted = runtime_session_service.create_session("task-interrupted")
    runtime_session_service.mark_interrupted(interrupted.id)
    stopped = runtime_session_service.create_session("task-stopped")
    runtime_session_service.mark_stopped(stopped.id)

    event_service.emit_event_sync(
        EventType.AGENT_LOOP_APPROVAL_REQUESTED,
        "Approval requested",
        metadata={"session_id": running.id, "approval_id": "approval-1"},
    )
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_APPROVAL_REQUESTED,
        "Approval requested",
        metadata={"session_id": completed.id, "approval_id": "approval-2"},
    )
    runtime_session_service.mark_completed(completed.id)


def test_runtime_dashboard(tmp_path) -> None:
    seed_sessions(tmp_path)
    client = TestClient(app)

    response = client.get("/runtime/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["active_sessions"] == 2
    assert body["pending_approvals"] == 2
    assert body["completed_today"] == 1
    assert body["failed_today"] == 1
    assert body["stopped_today"] == 1
    assert len(body["latest_sessions"]) == 5
