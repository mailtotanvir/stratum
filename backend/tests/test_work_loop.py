from fastapi.testclient import TestClient

from app.main import app
from app.services.tool_execution_service import tool_execution_service
from app.tools.tool_execution_adapter import MockToolExecutionAdapter, ToolExecutionResult


def create_session(client: TestClient) -> dict:
    run_response = client.post("/runtime/tasks/task-123/run")
    assert run_response.status_code == 200
    sessions_response = client.get("/runtime/sessions", params={"task_id": "task-123"})
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


def test_successful_single_step_work_loop() -> None:
    client = TestClient(app)
    session = create_session(client)
    create_tool(client)

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={
            "tool_name": "shell.read",
            "input_payload": {"path": "README.md"},
        },
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == session["id"]
    assert response.json()["tool_name"] == "shell.read"
    assert response.json()["invocation_id"]
    assert response.json()["status"] == "completed"


def test_work_loop_creates_invocation() -> None:
    client = TestClient(app)
    session = create_session(client)
    tool = create_tool(client)

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={"tool_name": "shell.read", "input_payload": {"path": "README.md"}},
    )
    invocations = client.get(
        "/tool-invocations",
        params={"session_id": session["id"], "tool_id": tool["id"]},
    )

    assert response.status_code == 200
    assert invocations.status_code == 200
    assert [invocation["id"] for invocation in invocations.json()] == [
        response.json()["invocation_id"]
    ]


def test_work_loop_execution_completed() -> None:
    client = TestClient(app)
    session = create_session(client)
    create_tool(client)

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={"tool_name": "shell.read", "input_payload": {"path": "README.md"}},
    )
    invocation = client.get(f"/tool-invocations/{response.json()['invocation_id']}")

    assert response.status_code == 200
    assert invocation.status_code == 200
    assert invocation.json()["status"] == "completed"
    assert invocation.json()["output_payload"] == {
        "mock": True,
        "tool": "shell.read",
    }


def test_work_loop_events_emitted() -> None:
    client = TestClient(app)
    session = create_session(client)
    create_tool(client)

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={"tool_name": "shell.read", "input_payload": {"path": "README.md"}},
    )
    trace_response = client.get("/trace")

    assert response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "work_loop_started" in event_types
    assert "work_loop_completed" in event_types


def test_work_loop_unknown_tool_returns_404() -> None:
    client = TestClient(app)
    session = create_session(client)

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={"tool_name": "missing.tool", "input_payload": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool not found: missing.tool"


def test_work_loop_unknown_session_returns_404() -> None:
    client = TestClient(app)
    create_tool(client)

    response = client.post(
        "/runtime/sessions/missing-session/work",
        json={"tool_name": "shell.read", "input_payload": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"


def test_work_loop_artifact_producing_execution_still_works(monkeypatch) -> None:
    client = TestClient(app)
    session = create_session(client)
    create_tool(client)
    monkeypatch.setattr(
        tool_execution_service,
        "_adapter",
        MockToolExecutionAdapter(
            ToolExecutionResult(
                success=True,
                output_payload={"mock": True, "tool": "shell.read"},
                artifacts=[
                    {
                        "path": "artifacts/task-123/work-loop.md",
                        "kind": "report",
                        "metadata": {"source": "work_loop_test"},
                    }
                ],
            )
        ),
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={"tool_name": "shell.read", "input_payload": {"path": "README.md"}},
    )
    invocation = client.get(f"/tool-invocations/{response.json()['invocation_id']}")
    artifact_id = invocation.json()["output_payload"]["artifacts"][0]
    attachments = client.get(
        "/runtime/tasks/task-123/artifacts",
        params={"session_id": session["id"]},
    )

    assert response.status_code == 200
    assert invocation.json()["status"] == "completed"
    assert [record["artifact_id"] for record in attachments.json()] == [artifact_id]


def test_work_loop_governance_block_still_works() -> None:
    client = TestClient(app)
    session = create_session(client)
    create_tool(client)
    client.post(
        "/demo/event",
        json={
            "type": "error",
            "severity": "critical",
            "message": "Critical failure",
            "metadata": {"source": "test"},
        },
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/work",
        json={"tool_name": "shell.read", "input_payload": {"path": "README.md"}},
    )
    invocation = client.get(f"/tool-invocations/{response.json()['invocation_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert invocation.json()["status"] == "failed"
    assert invocation.json()["output_payload"]["governance"]["decision"] == "block"
