from fastapi.testclient import TestClient

from app.main import app
from app.models.agent_execution import AgentExecutionMode
from app.models.provider_execution import ProviderMessageRole
from app.routes import runtime as runtime_routes
from app.services.event_service import event_service


client = TestClient(app)


def create_runtime() -> tuple[dict, dict]:
    run_response = client.post("/runtime/tasks/work-loop-agent-task/run")
    assert run_response.status_code == 200
    session = client.get(
        "/runtime/sessions",
        params={"task_id": "work-loop-agent-task"},
    ).json()[0]
    tool_response = client.post(
        "/tools",
        json={
            "name": "runtime.agent-test",
            "description": "Exercise the runtime agent boundary.",
        },
    )
    assert tool_response.status_code == 200
    return session, tool_response.json()


def run_work(session_id: str):
    return client.post(
        f"/runtime/sessions/{session_id}/work",
        json={
            "tool_name": "runtime.agent-test",
            "input_payload": {"request": "Execute deterministically"},
        },
    )


def persisted_event_types() -> list[str]:
    return [
        event.type.value
        for event in event_service.list_persisted_events()
    ]


class RecordingAgentExecution:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self._delegate.execute(request)


def test_work_loop_invokes_agent_execution_service(monkeypatch) -> None:
    session, _ = create_runtime()
    recorder = RecordingAgentExecution(
        runtime_routes.work_loop_service._agent_execution
    )
    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "_agent_execution",
        recorder,
    )

    response = run_work(session["id"])

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.runtime_session_id == session["id"]
    assert request.task_id == "work-loop-agent-task"
    assert request.provider == "mock"
    assert request.model == "mock-small"
    assert request.mode == AgentExecutionMode.SINGLE_TURN
    assert [message.role for message in request.messages] == [
        ProviderMessageRole.SYSTEM,
        ProviderMessageRole.USER,
    ]
    assert request.stream_mode.value == "none"


def test_work_loop_dispatches_provider_and_preserves_events() -> None:
    session, _ = create_runtime()

    response = run_work(session["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["agent_execution_id"].startswith("agent-execution-")
    assert body["provider_execution_id"].startswith("provider-execution-")
    event_types = persisted_event_types()
    for expected in (
        "work_loop_started",
        "tool_invocation_requested",
        "tool_invocation_running",
        "tool_execution_started",
        "tool_execution_completed",
        "agent_execution_requested",
        "agent_execution_started",
        "provider_execution_requested",
        "provider_execution_started",
        "provider_execution_completed",
        "agent_execution_completed",
        "work_loop_completed",
    ):
        assert expected in event_types


def test_agent_execution_failure_is_propagated_without_retry(
    monkeypatch,
) -> None:
    session, _ = create_runtime()
    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "_model",
        "missing-model",
    )

    response = run_work(session["id"])

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    event_types = persisted_event_types()
    assert event_types.count("agent_execution_requested") == 1
    assert event_types.count("provider_execution_requested") == 1
    assert "provider_execution_validation_failed" in event_types
    assert "provider_execution_failed" in event_types
    assert "agent_execution_failed" in event_types
    assert "work_loop_failed" in event_types


def test_runtime_session_execution_projection_is_updated() -> None:
    session, _ = create_runtime()

    run_work(session["id"])
    projection_response = client.get(
        f"/runtime/sessions/{session['id']}/agent-executions"
    )

    assert projection_response.status_code == 200
    projection = projection_response.json()
    assert projection["total_agent_executions"] == 1
    assert projection["completed_agent_executions"] == 1
    assert projection["total_provider_executions"] == 1
    assert projection["completed_provider_executions"] == 1


def test_runtime_reconstruction_remains_available() -> None:
    session, _ = create_runtime()

    run_work(session["id"])
    first_projection = client.get(
        f"/runtime/sessions/{session['id']}/agent-executions"
    )
    second_projection = client.get(
        f"/runtime/sessions/{session['id']}/agent-executions"
    )
    reconstruction = client.get(
        f"/runtime/reconstruction/sessions/{session['id']}"
    )

    assert first_projection.status_code == 200
    assert first_projection.json() == second_projection.json()
    assert reconstruction.status_code == 200
    assert reconstruction.json()["session_id"] == session["id"]


def test_repeated_work_execution_is_deterministic() -> None:
    session, _ = create_runtime()

    first = run_work(session["id"])
    second = run_work(session["id"])

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "completed"
    assert (
        first.json()["agent_execution_id"]
        == second.json()["agent_execution_id"]
    )
    assert (
        first.json()["provider_execution_id"]
        == second.json()["provider_execution_id"]
    )
