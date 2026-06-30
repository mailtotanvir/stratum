from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.services.event_service import event_service
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


def test_runtime_session_timeline(tmp_path) -> None:
    runtime_session_service.set_db_path(tmp_path / "sessions.db")
    event_service.set_trace_store(TraceService(tmp_path / "events.db"))
    session = runtime_session_service.create_session("task-1")
    runtime_session_service.mark_running(session.id)
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_STARTED,
        "Agent loop started",
        metadata={
            "session_id": session.id,
            "user_request": "Summarize the state",
            "provider_id": "mock",
            "model": "mock-small",
            "max_iterations": 2,
        },
    )
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_COMPLETED,
        "Agent loop completed",
        metadata={
            "session_id": session.id,
            "final_answer": "Done.",
        },
    )

    client = TestClient(app)
    response = client.get(f"/runtime/session/{session.id}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert [item["event_type"] for item in body] == [
        "agent_loop_started",
        "agent_loop_completed",
    ]
    assert body[0]["title"] == "Agent loop started"
    assert body[1]["payload"]["final_answer"] == "Done."
