import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.provider_execution import (
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.models.runtime_event import EventType, RuntimeEvent
from app.routes.agent_loop import (
    get_agent_loop_provider_execution_service,
)
from app.services.agent_loop_service import AgentLoopService
from app.services.event_service import event_service


class RouteProviderExecutionService:
    def __init__(self, tool: str = "final_answer") -> None:
        self.requests = []
        self.tool = tool

    def execute(self, request):
        self.requests.append(request)
        arguments = (
            {"answer": "Route answer."}
            if self.tool == "final_answer"
            else {"message": "Keep going."}
        )
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content=json.dumps(
                {
                    "tool": self.tool,
                    "arguments": arguments,
                }
            ),
        )


def test_agent_loop_route_uses_overridden_provider() -> None:
    provider = RouteProviderExecutionService()
    app.dependency_overrides[
        get_agent_loop_provider_execution_service
    ] = lambda: provider
    try:
        response = TestClient(app).post(
            "/agent-loop/run",
            json={
                "session_id": "route-loop-session",
                "user_request": "Answer through the route",
                "provider_id": "fake",
                "model": "fake-model",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["final_answer"] == "Route answer."
    assert body["iterations_used"] == 1
    assert provider.requests[0].runtime_session_id == "route-loop-session"


def test_agent_loop_smoke_route_completes_with_overridden_provider() -> None:
    provider = RouteProviderExecutionService()
    app.dependency_overrides[
        get_agent_loop_provider_execution_service
    ] = lambda: provider
    try:
        response = TestClient(app).post(
            "/agent-loop/smoke",
            json={"user_request": "Answer through the smoke route"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["final_answer"] == "Route answer."
    assert body["iterations_used"] == 1
    assert body["session_id"].startswith("agent-loop-smoke-")
    assert provider.requests[0].runtime_session_id == body["session_id"]


def test_agent_loop_smoke_route_defaults_to_three_iterations() -> None:
    provider = RouteProviderExecutionService(tool="observe")
    app.dependency_overrides[
        get_agent_loop_provider_execution_service
    ] = lambda: provider
    try:
        response = TestClient(app).post(
            "/agent-loop/smoke",
            json={"user_request": "Keep observing"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["iterations_used"] == 3
    assert len(provider.requests) == 3


def test_agent_loop_stop_route_persists_stop_request() -> None:
    response = TestClient(app).post(
        "/agent-loop/route-stop-session/stop",
        json={"reason": "Requested by user"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "route-stop-session",
        "stop_requested": True,
    }
    stop_event = [
        event
        for event in event_service.list_persisted_events(
            event_type="agent_loop_stop_requested"
        )
        if event.metadata.get("session_id") == "route-stop-session"
    ][-1]
    assert stop_event.metadata == {
        "session_id": "route-stop-session",
        "reason": "Requested by user",
    }


def test_agent_loop_event_history_matches_stream_for_requested_session() -> None:
    requested_provider = RouteProviderExecutionService()
    other_provider = RouteProviderExecutionService()
    AgentLoopService(
        provider_execution=requested_provider,
        events=event_service,
    ).run(
        _agent_loop_request("stream-session")
    )
    AgentLoopService(
        provider_execution=other_provider,
        events=event_service,
    ).run(
        _agent_loop_request("other-session")
    )

    client = TestClient(app)
    history_response = client.get("/agent-loop/events/stream-session")
    stream_response = client.get(
        "/agent-loop/events/stream-session/stream"
    )

    assert history_response.status_code == 200
    history = history_response.json()
    assert [event["type"] for event in history] == [
        "agent_loop_started",
        "agent_loop_provider_requested",
        "agent_loop_provider_completed",
        "agent_loop_tool_selected",
        "agent_loop_tool_completed",
        "agent_loop_completed",
    ]
    assert all(
        event["metadata"]["session_id"] == "stream-session"
        for event in history
    )
    assert all("id" in event and "ts" in event for event in history)

    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith(
        "text/event-stream"
    )
    blocks = [
        block for block in stream_response.text.split("\n\n") if block
    ]
    assert blocks
    assert "event: agent_loop_started" in stream_response.text
    assert "event: agent_loop_completed" in stream_response.text

    payloads = []
    for block in blocks:
        lines = block.splitlines()
        assert lines[0].startswith("event: agent_loop_")
        assert lines[1].startswith("data: ")
        payloads.append(json.loads(lines[1].removeprefix("data: ")))

    assert payloads == history
    assert "other-session" not in history_response.text
    assert "other-session" not in stream_response.text


def test_completed_agent_loop_run_summary_is_derived_from_history() -> None:
    AgentLoopService(
        provider_execution=RouteProviderExecutionService(),
        events=event_service,
    ).run(_agent_loop_request("completed-summary-session"))

    client = TestClient(app)
    history = client.get(
        "/agent-loop/events/completed-summary-session"
    ).json()
    response = client.get("/agent-loop/runs/completed-summary-session")

    assert response.status_code == 200
    summary = response.json()
    assert summary == {
        "session_id": "completed-summary-session",
        "status": "completed",
        "user_request": history[0]["metadata"]["user_request"],
        "provider_id": history[0]["metadata"]["provider_id"],
        "model": history[0]["metadata"]["model"],
        "iterations_used": history[-1]["metadata"]["iterations_used"],
        "final_answer": history[-1]["metadata"]["final_answer"],
        "error": None,
        "started_at": history[0]["ts"],
        "completed_at": history[-1]["ts"],
        "stopped_at": None,
    }


def test_failed_agent_loop_run_summary() -> None:
    AgentLoopService(
        provider_execution=RouteProviderExecutionService(tool="observe"),
        events=event_service,
    ).run(_agent_loop_request("failed-summary-session"))

    client = TestClient(app)
    history = client.get("/agent-loop/events/failed-summary-session").json()
    response = client.get("/agent-loop/runs/failed-summary-session")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "failed-summary-session",
        "status": "failed",
        "user_request": "Answer through the event stream",
        "provider_id": "fake",
        "model": "fake-model",
        "iterations_used": history[-1]["metadata"]["iterations_used"],
        "final_answer": None,
        "error": history[-1]["metadata"]["error"],
        "started_at": history[0]["ts"],
        "completed_at": history[-1]["ts"],
        "stopped_at": None,
    }


def test_stopped_agent_loop_run_summary() -> None:
    session_id = "stopped-summary-session"
    event_service.emit_event_sync(
        event_type="agent_loop_stop_requested",
        message="Agent loop stop requested",
        metadata={"session_id": session_id},
    )
    AgentLoopService(
        provider_execution=RouteProviderExecutionService(),
        events=event_service,
    ).run(_agent_loop_request(session_id))

    client = TestClient(app)
    history = client.get(f"/agent-loop/events/{session_id}").json()
    response = client.get(f"/agent-loop/runs/{session_id}")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "status": "stopped",
        "user_request": "Answer through the event stream",
        "provider_id": "fake",
        "model": "fake-model",
        "iterations_used": history[-1]["metadata"]["iterations_used"],
        "final_answer": None,
        "error": None,
        "started_at": history[1]["ts"],
        "completed_at": None,
        "stopped_at": history[-1]["ts"],
    }


def test_unknown_agent_loop_run_summary_returns_404() -> None:
    response = TestClient(app).get("/agent-loop/runs/unknown-session")

    assert response.status_code == 404


def test_stop_request_without_started_event_is_not_a_run() -> None:
    event_service.emit_event_sync(
        event_type=EventType.AGENT_LOOP_STOP_REQUESTED,
        message="Agent loop stop requested",
        metadata={"session_id": "stop-only-session"},
    )

    client = TestClient(app)

    assert client.get("/agent-loop/runs/stop-only-session").status_code == 404
    assert client.get("/agent-loop/runs").json() == []


def test_agent_loop_run_list_returns_multiple_terminal_statuses() -> None:
    _emit_run_events("completed-list-session", EventType.AGENT_LOOP_COMPLETED)
    _emit_run_events("failed-list-session", EventType.AGENT_LOOP_FAILED)
    _emit_run_events("stopped-list-session", EventType.AGENT_LOOP_STOPPED)

    response = TestClient(app).get("/agent-loop/runs")

    assert response.status_code == 200
    assert [
        (summary["session_id"], summary["status"])
        for summary in response.json()
    ] == [
        ("stopped-list-session", "stopped"),
        ("failed-list-session", "failed"),
        ("completed-list-session", "completed"),
    ]


def test_agent_loop_run_list_filters_status_and_applies_limit() -> None:
    _emit_run_events("failed-list-old", EventType.AGENT_LOOP_FAILED)
    _emit_run_events("completed-list", EventType.AGENT_LOOP_COMPLETED)
    _emit_run_events("failed-list-new", EventType.AGENT_LOOP_FAILED)

    response = TestClient(app).get(
        "/agent-loop/runs",
        params={"status": "failed", "limit": 1},
    )

    assert response.status_code == 200
    assert [
        summary["session_id"] for summary in response.json()
    ] == ["failed-list-new"]


def test_agent_loop_run_list_orders_tied_start_times_by_session_id(
    monkeypatch,
) -> None:
    events = [
        _started_event(1, "z-session", "2026-01-01T00:00:00+00:00"),
        _started_event(2, "a-session", "2026-01-01T00:00:00+00:00"),
        _started_event(3, "new-session", "2026-01-02T00:00:00+00:00"),
    ]
    monkeypatch.setattr(
        event_service,
        "list_persisted_events",
        lambda: events,
    )

    response = TestClient(app).get("/agent-loop/runs")

    assert response.status_code == 200
    assert [
        summary["session_id"] for summary in response.json()
    ] == ["new-session", "a-session", "z-session"]


def test_agent_loop_run_list_is_empty_when_no_runs_exist() -> None:
    response = TestClient(app).get("/agent-loop/runs")

    assert response.status_code == 200
    assert response.json() == []


def _emit_run_events(session_id: str, terminal_type: EventType) -> None:
    event_service.emit_event_sync(
        event_type=EventType.AGENT_LOOP_STARTED,
        message="Agent loop started",
        metadata={
            "session_id": session_id,
            "user_request": f"Run {session_id}",
            "provider_id": "fake",
            "model": "fake-model",
        },
    )
    terminal_metadata = {
        "session_id": session_id,
        "iterations_used": 1,
    }
    if terminal_type == EventType.AGENT_LOOP_COMPLETED:
        terminal_metadata["final_answer"] = "Done."
    elif terminal_type == EventType.AGENT_LOOP_FAILED:
        terminal_metadata["error"] = "Failed."
    event_service.emit_event_sync(
        event_type=terminal_type,
        message=f"Agent loop {terminal_type.value}",
        metadata=terminal_metadata,
    )


def _started_event(
    event_id: int,
    session_id: str,
    timestamp: str,
) -> RuntimeEvent:
    return RuntimeEvent(
        id=event_id,
        ts=timestamp,
        type=EventType.AGENT_LOOP_STARTED,
        message="Agent loop started",
        metadata={"session_id": session_id},
    )


def _agent_loop_request(session_id: str):
    from app.models.agent_loop import AgentLoopRequest

    return AgentLoopRequest(
        session_id=session_id,
        user_request="Answer through the event stream",
        provider_id="fake",
        model="fake-model",
    )
