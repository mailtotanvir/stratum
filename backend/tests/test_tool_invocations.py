from fastapi.testclient import TestClient

from app.main import app


def create_session(client: TestClient, task_id: str = "task-123") -> dict:
    run_response = client.post(f"/runtime/tasks/{task_id}/run")
    assert run_response.status_code == 200
    sessions_response = client.get("/runtime/sessions", params={"task_id": task_id})
    assert sessions_response.status_code == 200
    return sessions_response.json()[0]


def create_tool(client: TestClient, name: str = "shell.read") -> dict:
    response = client.post(
        "/tools",
        json={
            "name": name,
            "description": "Read a file from the workspace.",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_tool_invocation() -> None:
    client = TestClient(app)
    session = create_session(client)
    tool = create_tool(client)

    response = client.post(
        f"/runtime/sessions/{session['id']}/tools/{tool['id']}",
        json={"input_payload": {"path": "README.md"}},
    )

    assert response.status_code == 200
    invocation = response.json()
    assert invocation["session_id"] == session["id"]
    assert invocation["tool_id"] == tool["id"]
    assert invocation["input_payload"] == {"path": "README.md"}
    assert invocation["output_payload"] is None
    assert invocation["created_at"] is not None


def test_tool_invocation_transitions_to_running() -> None:
    client = TestClient(app)
    session = create_session(client)
    tool = create_tool(client)

    response = client.post(f"/runtime/sessions/{session['id']}/tools/{tool['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["completed_at"] is None


def test_list_tool_invocations_by_session() -> None:
    client = TestClient(app)
    first_session = create_session(client, task_id="task-123")
    second_session = create_session(client, task_id="task-456")
    tool = create_tool(client)
    expected = client.post(
        f"/runtime/sessions/{first_session['id']}/tools/{tool['id']}"
    ).json()
    client.post(f"/runtime/sessions/{second_session['id']}/tools/{tool['id']}")

    response = client.get(
        "/tool-invocations",
        params={"session_id": first_session["id"]},
    )

    assert response.status_code == 200
    assert response.json() == [expected]


def test_list_tool_invocations_by_tool() -> None:
    client = TestClient(app)
    session = create_session(client)
    first_tool = create_tool(client, name="shell.read")
    second_tool = create_tool(client, name="shell.write")
    expected = client.post(
        f"/runtime/sessions/{session['id']}/tools/{first_tool['id']}"
    ).json()
    client.post(f"/runtime/sessions/{session['id']}/tools/{second_tool['id']}")

    response = client.get(
        "/tool-invocations",
        params={"tool_id": first_tool["id"]},
    )

    assert response.status_code == 200
    assert response.json() == [expected]


def test_tool_invocation_unknown_session_returns_404() -> None:
    client = TestClient(app)
    tool = create_tool(client)

    response = client.post(f"/runtime/sessions/missing-session/tools/{tool['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"


def test_tool_invocation_unknown_tool_returns_404() -> None:
    client = TestClient(app)
    session = create_session(client)

    response = client.post(f"/runtime/sessions/{session['id']}/tools/missing-tool")

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool not found: missing-tool"


def test_tool_invocation_events_appear_in_trace() -> None:
    client = TestClient(app)
    session = create_session(client)
    tool = create_tool(client)

    invocation = client.post(
        f"/runtime/sessions/{session['id']}/tools/{tool['id']}",
        json={"input_payload": {"path": "README.md"}},
    ).json()
    trace_response = client.get("/trace", params={"type": "tool_invocation_running"})

    assert trace_response.status_code == 200
    events = trace_response.json()
    assert len(events) == 1
    assert events[0]["metadata"]["tool_invocation_id"] == invocation["id"]
    assert events[0]["metadata"]["session_id"] == session["id"]
    assert events[0]["metadata"]["tool_id"] == tool["id"]
    assert events[0]["metadata"]["input_payload"] == {"path": "README.md"}


def test_tool_invocation_persistence_survives_retrieval() -> None:
    client = TestClient(app)
    session = create_session(client)
    tool = create_tool(client)

    created = client.post(
        f"/runtime/sessions/{session['id']}/tools/{tool['id']}",
        json={"input_payload": {"path": "README.md"}},
    ).json()
    response = client.get(f"/tool-invocations/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created
