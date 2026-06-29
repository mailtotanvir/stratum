import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.event_service import event_service


client = TestClient(app)


def request_body(
    *,
    provider: str = "mock",
    model: str = "mock-small",
    content: str = "Execute this deterministic request",
) -> dict:
    return {
        "runtime_session_id": "route-session-1",
        "task_id": "route-task-1",
        "provider": provider,
        "model": model,
        "mode": "single_turn",
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "stream_mode": "none",
        "correlation_id": "route-correlation-1",
        "metadata": {"source": "agent-execution-route-test"},
    }


def test_agent_execution_route_completes_mock_request() -> None:
    response = client.post(
        "/runtime/agent-execution",
        json=request_body(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["id"].startswith("agent-execution-")
    assert body["result"]["provider_execution_record_id"].startswith(
        "provider-execution-"
    )
    assert body["result"]["provider_result"]["content"] == "Mock response."


def test_invalid_provider_model_returns_failed_record() -> None:
    response = client.post(
        "/runtime/agent-execution",
        json=request_body(provider="missing", model="missing"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["result"]["status"] == "failed"
    assert "unknown_model" in body["result"]["provider_result"][
        "error_message"
    ]


def test_route_events_exclude_prompt_content() -> None:
    secret = "route-prompt-must-not-appear-in-events"

    response = client.post(
        "/runtime/agent-execution",
        json=request_body(content=secret),
    )

    assert response.status_code == 200
    events = event_service.list_persisted_events()
    assert [event.type.value for event in events] == [
        "agent_execution_requested",
        "agent_execution_started",
        "provider_execution_requested",
        "provider_execution_started",
        "provider_execution_completed",
        "agent_execution_completed",
    ]
    for event in events:
        serialized = json.dumps(event.metadata, sort_keys=True)
        assert secret not in serialized
        assert "messages" not in event.metadata
        assert "content" not in event.metadata


def test_repeated_route_calls_have_deterministic_results() -> None:
    first = client.post(
        "/runtime/agent-execution",
        json=request_body(),
    )
    second = client.post(
        "/runtime/agent-execution",
        json=request_body(),
    )

    assert first.status_code == second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["status"] == second_body["status"] == "completed"
    assert first_body["request"] == second_body["request"]
    assert first_body["result"] == second_body["result"]
