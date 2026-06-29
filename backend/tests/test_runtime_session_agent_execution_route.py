import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.event_service import event_service
from app.services.runtime_session_service import runtime_session_service


client = TestClient(app)


def request_body(
    *,
    provider: str = "mock",
    model: str = "mock-small",
    content: str = "Session-scoped agent request",
) -> dict:
    return {
        "runtime_session_id": "body-session-must-be-overridden",
        "task_id": "session-agent-task",
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
        "correlation_id": "session-agent-correlation",
        "metadata": {"source": "runtime-session-route-test"},
    }


def create_session() -> str:
    return runtime_session_service.create_session(
        "runtime-session-owner-task"
    ).id


def execute(
    session_id: str,
    *,
    provider: str = "mock",
    model: str = "mock-small",
    content: str = "Session-scoped agent request",
):
    return client.post(
        f"/runtime/sessions/{session_id}/agent-execution",
        json=request_body(
            provider=provider,
            model=model,
            content=content,
        ),
    )


def test_session_agent_execution_route_completes_mock_request() -> None:
    session_id = create_session()

    response = execute(session_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["request"]["runtime_session_id"] == session_id
    assert body["result"]["provider_result"]["content"] == "Mock response."


def test_path_session_overrides_body_and_preserves_request_identity() -> None:
    session_id = create_session()

    body = execute(session_id).json()

    assert body["request"]["runtime_session_id"] == session_id
    assert body["request"]["task_id"] == "session-agent-task"
    assert body["request"]["correlation_id"] == "session-agent-correlation"
    assert body["result"]["provider_execution_record_id"].startswith(
        "provider-execution-"
    )


def test_provider_events_carry_normalized_runtime_identity() -> None:
    session_id = create_session()

    response = execute(session_id)

    assert response.status_code == 200
    provider_events = [
        event
        for event in event_service.list_persisted_events()
        if event.type.value.startswith("provider_execution_")
    ]
    assert provider_events
    for event in provider_events:
        assert event.metadata["runtime_session_id"] == session_id
        assert event.metadata["task_id"] == "session-agent-task"
        assert event.metadata["correlation_id"] == (
            "session-agent-correlation"
        )
        assert event.metadata["message_count"] == 1


def test_runtime_events_use_path_session_and_exclude_prompt() -> None:
    session_id = create_session()
    secret = "session-route-prompt-must-not-be-emitted"

    response = execute(session_id, content=secret)

    assert response.status_code == 200
    events = event_service.list_persisted_events()
    assert events
    for event in events:
        assert event.metadata["runtime_session_id"] == session_id
        assert event.metadata["message_count"] == 1
        serialized = json.dumps(event.metadata, sort_keys=True)
        assert secret not in serialized
        assert "messages" not in event.metadata
        assert "content" not in event.metadata


def test_invalid_provider_model_returns_failed_record() -> None:
    session_id = create_session()

    response = execute(
        session_id,
        provider="missing",
        model="missing",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "unknown_model" in body["result"]["provider_result"][
        "error_message"
    ]
