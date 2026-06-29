from app.models.agent_execution import (
    AgentExecutionMode,
    AgentExecutionRequest,
    AgentExecutionStatus,
)
from app.models.provider_execution import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.services.agent_execution_service import AgentExecutionService
from app.services.event_service import EventService
from app.services.provider_execution_service import ProviderExecutionService
from app.services.trace_service import TraceService


def request(
    *,
    model: str = "mock-large",
    mode: AgentExecutionMode = AgentExecutionMode.SINGLE_TURN,
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        runtime_session_id="session-1",
        task_id="task-1",
        provider="mock",
        model=model,
        mode=mode,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Execute this request",
            )
        ],
        stream_mode=ProviderStreamMode.NONE,
        correlation_id="correlation-1",
        metadata={"source": "agent-test"},
    )


def event_service(tmp_path) -> EventService:
    return EventService(TraceService(tmp_path / "agent-execution-events.db"))


def test_successful_execution() -> None:
    record = AgentExecutionService().execute(request())

    assert record.status == AgentExecutionStatus.COMPLETED
    assert record.result is not None
    assert record.result.status == AgentExecutionStatus.COMPLETED
    assert record.result.provider_result is not None
    assert record.result.provider_result.content == "Mock response."


def test_provider_failure_propagates() -> None:
    record = AgentExecutionService().execute(request(model="missing"))

    assert record.status == AgentExecutionStatus.FAILED
    assert record.result is not None
    assert record.result.status == AgentExecutionStatus.FAILED
    assert record.result.provider_result is not None
    assert "unknown_model" in record.result.provider_result.error_message


def test_provider_execution_id_is_copied() -> None:
    record = AgentExecutionService().execute(request())

    assert record.result is not None
    assert record.result.provider_execution_record_id is not None
    assert record.result.provider_execution_record_id.startswith(
        "provider-execution-"
    )


def test_runtime_events_are_emitted_without_prompt_content(tmp_path) -> None:
    events = event_service(tmp_path)
    record = AgentExecutionService(events=events).execute(request())
    emitted = events.list_persisted_events()

    assert [event.type.value for event in emitted] == [
        "agent_execution_requested",
        "agent_execution_started",
        "agent_execution_completed",
    ]
    assert emitted[-1].metadata == {
        "agent_execution_id": record.id,
        "provider_execution_id": (
            record.result.provider_execution_record_id
        ),
        "provider": "mock",
        "model": "mock-large",
        "runtime_session_id": "session-1",
        "task_id": "task-1",
        "correlation_id": "correlation-1",
        "status": "completed",
        "message_count": 1,
    }
    for event in emitted:
        assert "messages" not in event.metadata
        assert "content" not in event.metadata


def test_failed_execution_emits_failed_event(tmp_path) -> None:
    events = event_service(tmp_path)

    AgentExecutionService(events=events).execute(request(model="missing"))

    assert [
        event.type.value for event in events.list_persisted_events()
    ] == [
        "agent_execution_requested",
        "agent_execution_started",
        "agent_execution_failed",
    ]


def test_metadata_is_preserved_across_execution_boundary() -> None:
    record = AgentExecutionService().execute(request())

    assert record.metadata == {"source": "agent-test"}
    assert record.result is not None
    assert record.result.metadata == {"source": "agent-test"}
    assert record.result.provider_result is not None


def test_completed_at_is_populated() -> None:
    record = AgentExecutionService().execute(request())

    assert record.completed_at is not None
    assert record.completed_at >= record.created_at


def test_ids_and_statuses_are_deterministic() -> None:
    service = AgentExecutionService()

    first = service.execute(request())
    second = service.execute(request())

    assert first.id == second.id
    assert first.status == second.status == AgentExecutionStatus.COMPLETED


def test_tool_enabled_maps_to_provider_tool_call() -> None:
    record = AgentExecutionService().execute(
        request(mode=AgentExecutionMode.TOOL_ENABLED)
    )

    assert record.status == AgentExecutionStatus.COMPLETED
    assert record.result is not None
    assert record.result.provider_result is not None
    assert record.result.provider_result.content == "Mock tool call."
