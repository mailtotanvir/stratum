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


def create_tool(client: TestClient, enabled: bool = True) -> dict:
    response = client.post(
        "/tools",
        json={
            "name": "shell.read",
            "description": "Read a file from the workspace.",
            "enabled": enabled,
        },
    )
    assert response.status_code == 200
    return response.json()


def create_invocation(client: TestClient, enabled: bool = True) -> dict:
    session = create_session(client)
    tool = create_tool(client, enabled=enabled)
    response = client.post(
        f"/runtime/sessions/{session['id']}/tools/{tool['id']}",
        json={"input_payload": {"path": "README.md"}},
    )
    assert response.status_code == 200
    return response.json()


def test_execute_tool_invocation() -> None:
    client = TestClient(app)
    invocation = create_invocation(client)

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")

    assert response.status_code == 200
    assert response.json()["id"] == invocation["id"]
    assert response.json()["status"] == "completed"
    assert response.json()["output_payload"] == {
        "mock": True,
        "tool": "shell.read",
    }


def test_execute_tool_invocation_stores_output_payload() -> None:
    client = TestClient(app)
    invocation = create_invocation(client)

    execute_response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    get_response = client.get(f"/tool-invocations/{invocation['id']}")

    assert execute_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["output_payload"] == {
        "mock": True,
        "tool": "shell.read",
    }
    assert get_response.json()["completed_at"] is not None


def test_execute_tool_invocation_with_artifact_creates_artifact_record(
    monkeypatch,
) -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    monkeypatch.setattr(
        tool_execution_service,
        "_adapter",
        MockToolExecutionAdapter(
            ToolExecutionResult(
                success=True,
                output_payload={"mock": True, "tool": "shell.read"},
                artifacts=[
                    {
                        "path": "artifacts/task-123/tool-output.md",
                        "kind": "report",
                        "metadata": {"source": "mock"},
                    }
                ],
            )
        ),
    )

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    artifact_id = response.json()["output_payload"]["artifacts"][0]
    artifact_response = client.get(f"/artifacts/{artifact_id}")

    assert response.status_code == 200
    assert artifact_response.status_code == 200
    assert artifact_response.json()["path"] == "artifacts/task-123/tool-output.md"
    assert artifact_response.json()["kind"] == "report"
    assert artifact_response.json()["metadata"] == {"source": "mock"}


def test_tool_execution_artifact_is_attached_to_runtime_task_session(
    monkeypatch,
) -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    monkeypatch.setattr(
        tool_execution_service,
        "_adapter",
        MockToolExecutionAdapter(
            ToolExecutionResult(
                success=True,
                output_payload={"mock": True, "tool": "shell.read"},
                artifacts=[
                    {
                        "path": "artifacts/task-123/tool-output.md",
                        "kind": "summary",
                        "metadata": {"source": "mock"},
                    }
                ],
            )
        ),
    )

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    artifact_id = response.json()["output_payload"]["artifacts"][0]
    attached_response = client.get(
        "/runtime/tasks/task-123/artifacts",
        params={"session_id": invocation["session_id"]},
    )

    assert response.status_code == 200
    assert attached_response.status_code == 200
    assert [record["artifact_id"] for record in attached_response.json()] == [
        artifact_id
    ]
    assert attached_response.json()[0]["session_id"] == invocation["session_id"]


def test_tool_execution_output_payload_includes_artifact_ids(monkeypatch) -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    monkeypatch.setattr(
        tool_execution_service,
        "_adapter",
        MockToolExecutionAdapter(
            ToolExecutionResult(
                success=True,
                output_payload={"mock": True, "tool": "shell.read"},
                artifacts=[
                    {
                        "path": "artifacts/task-123/tool-output.md",
                        "kind": "log",
                        "metadata": {"source": "mock"},
                    }
                ],
            )
        ),
    )

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")

    assert response.status_code == 200
    assert response.json()["output_payload"]["mock"] is True
    assert len(response.json()["output_payload"]["artifacts"]) == 1


def test_tool_execution_artifact_events_appear_in_trace(monkeypatch) -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    monkeypatch.setattr(
        tool_execution_service,
        "_adapter",
        MockToolExecutionAdapter(
            ToolExecutionResult(
                success=True,
                output_payload={"mock": True, "tool": "shell.read"},
                artifacts=[
                    {
                        "path": "artifacts/task-123/tool-output.md",
                        "kind": "file",
                        "metadata": {"source": "mock"},
                    }
                ],
            )
        ),
    )

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "artifact_created" in event_types
    assert "runtime_artifact_attached" in event_types


def test_tool_execution_invalid_artifact_kind_fails_invocation(monkeypatch) -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    monkeypatch.setattr(
        tool_execution_service,
        "_adapter",
        MockToolExecutionAdapter(
            ToolExecutionResult(
                success=True,
                output_payload={"mock": True, "tool": "shell.read"},
                artifacts=[
                    {
                        "path": "artifacts/task-123/tool-output.bin",
                        "kind": "binary",
                        "metadata": {"source": "mock"},
                    }
                ],
            )
        ),
    )

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    trace_response = client.get("/trace", params={"type": "tool_execution_failed"})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["output_payload"] == {
        "error_message": "Invalid artifact kind: binary"
    }
    assert trace_response.status_code == 200
    assert len(trace_response.json()) == 1


def test_tool_execution_events_appear_in_trace() -> None:
    client = TestClient(app)
    invocation = create_invocation(client)

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    trace_response = client.get("/trace")

    assert response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "tool_execution_started" in event_types
    assert "tool_execution_completed" in event_types


def test_tool_execution_warning_emits_warning_and_still_executes() -> None:
    client = TestClient(app)
    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    invocation = create_invocation(client)

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    trace_response = client.get(
        "/trace",
        params={"type": "tool_execution_governance_warning"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["output_payload"] == {
        "mock": True,
        "tool": "shell.read",
    }
    events = trace_response.json()
    assert len(events) == 1
    assert events[0]["metadata"]["invocation_id"] == invocation["id"]
    assert events[0]["metadata"]["decision"] == "warn"
    assert events[0]["metadata"]["reasons"] == ["governance_degraded"]


def test_tool_execution_block_emits_blocked_and_does_not_execute_adapter() -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    client.post(
        "/demo/event",
        json={
            "type": "error",
            "severity": "critical",
            "message": "Critical failure",
            "metadata": {"source": "test"},
        },
    )

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["output_payload"] == {
        "governance": {
            "decision": "block",
            "reasons": ["critical_event_present", "error_budget_exhausted"],
        },
    }
    event_types = [event["type"] for event in trace_response.json()]
    assert "tool_execution_governance_blocked" in event_types
    assert "tool_execution_started" not in event_types
    assert "tool_execution_completed" not in event_types


def test_blocked_tool_execution_persists_failed_invocation() -> None:
    client = TestClient(app)
    invocation = create_invocation(client)
    client.post(
        "/demo/event",
        json={
            "type": "error",
            "severity": "critical",
            "message": "Critical failure",
            "metadata": {"source": "test"},
        },
    )

    client.post(f"/tool-invocations/{invocation['id']}/execute")
    get_response = client.get(f"/tool-invocations/{invocation['id']}")

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "failed"
    assert get_response.json()["completed_at"] is not None
    assert get_response.json()["output_payload"]["governance"]["decision"] == "block"


def test_tool_execution_governance_events_appear_in_trace() -> None:
    client = TestClient(app)
    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    invocation = create_invocation(client)

    client.post(f"/tool-invocations/{invocation['id']}/execute")
    trace_response = client.get("/trace")

    assert trace_response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "tool_execution_governance_warning" in event_types


def test_execute_unknown_tool_invocation_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/tool-invocations/missing-invocation/execute")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Tool invocation not found: missing-invocation"
    )


def test_execute_invocation_for_disabled_tool_returns_409() -> None:
    client = TestClient(app)
    invocation = create_invocation(client, enabled=False)

    response = client.post(f"/tool-invocations/{invocation['id']}/execute")

    assert response.status_code == 409
    assert response.json()["detail"] == f"Tool is disabled: {invocation['tool_id']}"
    trace_response = client.get("/trace")
    event_types = [event["type"] for event in trace_response.json()]
    assert "tool_execution_governance_warning" not in event_types
    assert "tool_execution_governance_blocked" not in event_types
