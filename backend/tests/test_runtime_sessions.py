from fastapi.testclient import TestClient

from app.main import app


def test_session_created_on_run() -> None:
    client = TestClient(app)

    run_response = client.post("/runtime/tasks/task-123/run")
    sessions_response = client.get("/runtime/sessions", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 1
    assert sessions[0]["task_id"] == "task-123"
    assert sessions[0]["created_at"] is not None


def test_session_transitions_to_running() -> None:
    client = TestClient(app)

    client.post("/runtime/tasks/task-123/run")
    session = client.get("/runtime/sessions", params={"task_id": "task-123"}).json()[0]
    get_response = client.get(f"/runtime/sessions/{session['id']}")

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "running"
    assert get_response.json()["completed_at"] is None


def test_interrupt_updates_session() -> None:
    client = TestClient(app)

    client.post("/runtime/tasks/task-123/run")
    client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    session = client.get("/runtime/sessions", params={"task_id": "task-123"}).json()[0]

    assert session["status"] == "interrupted"
    assert session["completed_at"] is not None


def test_stop_updates_session() -> None:
    client = TestClient(app)

    client.post("/runtime/tasks/task-123/run")
    client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    session = client.get("/runtime/sessions", params={"task_id": "task-123"}).json()[0]

    assert session["status"] == "stopped"
    assert session["completed_at"] is not None


def test_list_sessions_by_task_id() -> None:
    client = TestClient(app)

    client.post("/runtime/tasks/task-123/run")
    client.post("/runtime/tasks/task-456/run")
    response = client.get("/runtime/sessions", params={"task_id": "task-123"})

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["task_id"] == "task-123"


def test_runtime_session_events_appear_in_trace() -> None:
    client = TestClient(app)

    run_response = client.post("/runtime/tasks/task-123/run")
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert trace_response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "runtime_session_created" in event_types
    assert "runtime_session_running" in event_types


def test_unknown_runtime_session_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/runtime/sessions/missing-session")

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"
