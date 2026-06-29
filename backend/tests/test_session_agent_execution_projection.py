import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.agent_execution import (
    AgentExecutionMode,
    AgentExecutionRequest,
)
from app.models.provider_execution import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.models.runtime_event import EventType
from app.runtime.projection_registry import projection_registry
from app.services.agent_execution_service import AgentExecutionService
from app.services.event_service import EventService
from app.services.projection_registry_service import (
    projection_registry_service,
)
from app.services.provider_execution_service import ProviderExecutionService
from app.services.runtime_session_service import runtime_session_service
from app.services.session_agent_execution_projection_builder_service import (
    SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
    SessionAgentExecutionProjectionBuilderService,
)
from app.services.trace_service import TraceService


client = TestClient(app)


def event_service(tmp_path) -> EventService:
    return EventService(
        TraceService(tmp_path / "session-agent-execution-events.db")
    )


def agent_request(
    session_id: str,
    *,
    provider: str = "mock",
    model: str = "mock-small",
    content: str = "Projection test prompt",
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        runtime_session_id=session_id,
        task_id="projection-task",
        provider=provider,
        model=model,
        mode=AgentExecutionMode.SINGLE_TURN,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=content,
            )
        ],
        stream_mode=ProviderStreamMode.NONE,
        correlation_id=f"correlation-{session_id}",
    )


def execute_agent(
    events: EventService,
    request: AgentExecutionRequest,
) -> None:
    AgentExecutionService(
        provider_execution=ProviderExecutionService(events=events),
        events=events,
    ).execute(request)


def test_empty_session_returns_empty_projection(tmp_path) -> None:
    projection = SessionAgentExecutionProjectionBuilderService(
        event_service(tmp_path)
    ).build("empty-session")

    assert projection.runtime_session_id == "empty-session"
    assert projection.executions == []
    assert projection.total_agent_executions == 0
    assert projection.completed_agent_executions == 0
    assert projection.failed_agent_executions == 0
    assert projection.total_provider_executions == 0
    assert projection.completed_provider_executions == 0
    assert projection.failed_provider_executions == 0
    assert projection.metadata == {}


def test_successful_mock_execution_appears_with_completed_counts(
    tmp_path,
) -> None:
    events = event_service(tmp_path)
    execute_agent(events, agent_request("successful-session"))

    projection = SessionAgentExecutionProjectionBuilderService(
        events
    ).build("successful-session")

    assert len(projection.executions) == 1
    execution = projection.executions[0]
    assert execution.agent_execution_id is not None
    assert execution.provider_execution_id is not None
    assert execution.provider == "mock"
    assert execution.model == "mock-small"
    assert execution.task_id == "projection-task"
    assert execution.correlation_id == "correlation-successful-session"
    assert execution.status == "completed"
    assert execution.started_at is not None
    assert execution.completed_at is not None
    assert execution.usage == {
        "input_tokens": 3,
        "output_tokens": 2,
        "total_tokens": 5,
        "estimated_cost": 0.0,
        "currency": "USD",
    }
    assert projection.total_agent_executions == 1
    assert projection.completed_agent_executions == 1
    assert projection.failed_agent_executions == 0
    assert projection.total_provider_executions == 1
    assert projection.completed_provider_executions == 1
    assert projection.failed_provider_executions == 0


def test_failed_provider_execution_appears_with_failed_counts(
    tmp_path,
) -> None:
    events = event_service(tmp_path)
    execute_agent(
        events,
        agent_request(
            "failed-session",
            provider="missing",
            model="missing",
        ),
    )

    projection = SessionAgentExecutionProjectionBuilderService(
        events
    ).build("failed-session")

    assert len(projection.executions) == 1
    assert projection.executions[0].status == "failed"
    assert "unknown_model" in projection.executions[0].error_message
    assert projection.total_agent_executions == 1
    assert projection.failed_agent_executions == 1
    assert projection.total_provider_executions == 1
    assert projection.failed_provider_executions == 1


def test_projection_ignores_other_sessions(tmp_path) -> None:
    events = event_service(tmp_path)
    execute_agent(events, agent_request("included-session"))
    execute_agent(events, agent_request("other-session"))

    projection = SessionAgentExecutionProjectionBuilderService(
        events
    ).build("included-session")

    assert projection.total_agent_executions == 1
    assert projection.total_provider_executions == 1
    assert all(
        execution.correlation_id == "correlation-included-session"
        for execution in projection.executions
    )


def test_projection_excludes_prompt_and_message_content(tmp_path) -> None:
    events = event_service(tmp_path)
    secret = "projection-must-not-expose-this-prompt"
    execute_agent(
        events,
        agent_request("safe-session", content=secret),
    )

    projection = SessionAgentExecutionProjectionBuilderService(
        events
    ).build("safe-session")
    serialized = json.dumps(projection.model_dump(mode="json"))

    assert secret not in serialized
    assert "messages" not in serialized


def test_provider_only_events_are_retained(tmp_path) -> None:
    events = event_service(tmp_path)
    common_metadata = {
        "runtime_session_id": "provider-only-session",
        "provider_execution_record_id": "provider-only-1",
        "provider": "mock",
        "model": "mock-small",
        "task_id": "provider-only-task",
        "correlation_id": "provider-only-correlation",
        "message_count": 1,
    }
    events.emit_event_sync(
        EventType.PROVIDER_EXECUTION_REQUESTED,
        "Provider execution requested",
        metadata={**common_metadata, "status": "requested"},
    )
    events.emit_event_sync(
        EventType.PROVIDER_EXECUTION_STARTED,
        "Provider execution started",
        metadata={**common_metadata, "status": "requested"},
    )
    events.emit_event_sync(
        EventType.PROVIDER_EXECUTION_COMPLETED,
        "Provider execution completed",
        metadata={
            **common_metadata,
            "status": "completed",
            "usage": {"total_tokens": 4},
        },
    )

    projection = SessionAgentExecutionProjectionBuilderService(
        events
    ).build("provider-only-session")

    assert len(projection.executions) == 1
    execution = projection.executions[0]
    assert execution.agent_execution_id is None
    assert execution.provider_execution_id == "provider-only-1"
    assert execution.status == "completed"
    assert execution.usage == {"total_tokens": 4}
    assert projection.total_agent_executions == 0
    assert projection.total_provider_executions == 1
    assert projection.completed_provider_executions == 1


def test_projection_is_deterministic_across_rebuilds(tmp_path) -> None:
    events = event_service(tmp_path)
    execute_agent(events, agent_request("deterministic-session"))
    builder = SessionAgentExecutionProjectionBuilderService(events)

    first = builder.build("deterministic-session")
    second = builder.build("deterministic-session")

    assert first == second
    assert first is not second
    assert first.executions is not second.executions


def test_projection_is_registered() -> None:
    assert (
        projection_registry.get(SESSION_AGENT_EXECUTION_PROJECTION_TYPE)
        is not None
    )
    detail = projection_registry_service.get(
        SESSION_AGENT_EXECUTION_PROJECTION_TYPE
    )
    assert detail.capabilities.reconstructable is True
    assert detail.route == (
        "/runtime/sessions/{runtime_session_id}/agent-executions"
    )


def test_projection_route_returns_200() -> None:
    session = runtime_session_service.create_session(
        "projection-route-task"
    )
    execute_response = client.post(
        f"/runtime/sessions/{session.id}/agent-execution",
        json={
            "runtime_session_id": "body-session",
            "task_id": "projection-route-task",
            "provider": "mock",
            "model": "mock-small",
            "mode": "single_turn",
            "messages": [{"role": "user", "content": "Route projection"}],
            "stream_mode": "none",
            "correlation_id": "projection-route-correlation",
        },
    )

    response = client.get(
        f"/runtime/sessions/{session.id}/agent-executions"
    )

    assert execute_response.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["runtime_session_id"] == session.id
    assert body["total_agent_executions"] == 1
    assert body["completed_agent_executions"] == 1
