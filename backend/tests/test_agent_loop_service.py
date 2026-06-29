import json

from app.models.agent_loop import AgentLoopRequest, AgentLoopStatus
from app.models.provider_execution import (
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderMessageRole,
)
from app.models.runtime_event import EventType
from app.services.agent_loop_prompt_builder_service import (
    AGENT_LOOP_SYSTEM_PROMPT,
)
from app.services.agent_loop_service import AgentLoopService
from app.services.event_service import EventService
from app.services.trace_service import TraceService


class StubProviderExecutionService:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content=self.outputs[len(self.requests) - 1],
        )


def request(max_iterations: int = 5) -> AgentLoopRequest:
    return AgentLoopRequest(
        session_id="loop-session-1",
        user_request="Produce an answer",
        max_iterations=max_iterations,
        provider_id="fake",
        model="fake-model",
    )


def service(
    tmp_path,
    outputs: list[str],
) -> tuple[AgentLoopService, StubProviderExecutionService, EventService]:
    provider = StubProviderExecutionService(outputs)
    events = EventService(TraceService(tmp_path / "agent-loop.db"))
    return (
        AgentLoopService(
            provider_execution=provider,
            events=events,
        ),
        provider,
        events,
    )


def tool_output(tool: str, arguments: dict[str, str]) -> str:
    return json.dumps({"tool": tool, "arguments": arguments})


def test_loop_completes_on_final_answer(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Done."})],
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.final_answer == "Done."
    assert result.iterations_used == 1
    assert result.steps[0].tool_result is not None
    assert result.steps[0].tool_result.completion_intent is True
    assert len(provider.requests) == 1
    persisted_events = events.list_persisted_events()
    assert [event.type.value for event in persisted_events] == [
        "agent_loop_started",
        "agent_loop_provider_requested",
        "agent_loop_provider_completed",
        "agent_loop_tool_selected",
        "agent_loop_tool_completed",
        "agent_loop_completed",
    ]
    assert [event.metadata for event in persisted_events] == [
        {
            "session_id": "loop-session-1",
            "user_request": "Produce an answer",
            "max_iterations": 5,
            "provider_id": "fake",
            "model": "fake-model",
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "provider_id": "fake",
            "model": "fake-model",
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "status": "completed",
            "provider_id": "fake",
            "model": "fake-model",
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "tool": "final_answer",
            "arguments": {"answer": "Done."},
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "tool": "final_answer",
            "output": "Done.",
            "completion_intent": True,
        },
        {
            "session_id": "loop-session-1",
            "status": "completed",
            "final_answer": "Done.",
            "iterations_used": 1,
        },
    ]


def test_loop_fails_on_invalid_json(tmp_path) -> None:
    loop, _, events = service(tmp_path, ["not JSON"])

    result = loop.run(request())

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 1
    assert "Invalid agent loop provider output" in result.error
    failed_event = events.list_persisted_events()[-1]
    assert failed_event.type.value == "agent_loop_failed"
    assert failed_event.metadata == {
        "session_id": "loop-session-1",
        "status": "failed",
        "error": result.error,
        "iterations_used": 1,
    }


def test_loop_stops_before_provider_call_when_stop_requested(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Not reached"})],
    )
    events.emit_event_sync(
        event_type=EventType.AGENT_LOOP_STOP_REQUESTED,
        message="Agent loop stop requested",
        metadata={
            "session_id": "loop-session-1",
            "reason": "Requested by user",
        },
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.STOPPED
    assert result.iterations_used == 0
    assert provider.requests == []
    stopped_event = events.list_persisted_events()[-1]
    assert stopped_event.type == EventType.AGENT_LOOP_STOPPED
    assert stopped_event.metadata == {
        "session_id": "loop-session-1",
        "status": "stopped",
        "iterations_used": 0,
        "reason": "Requested by user",
    }


def test_loop_fails_on_unknown_tool(tmp_path) -> None:
    loop, _, _ = service(
        tmp_path,
        [tool_output("write_file", {"path": "unsafe"})],
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 1
    assert result.error == "Unknown agent loop tool: write_file"


def test_loop_respects_max_iterations(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output("observe", {"message": "First observation"}),
            tool_output("observe", {"message": "Second observation"}),
        ],
    )

    result = loop.run(request(max_iterations=2))

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 2
    assert len(result.steps) == 2
    assert len(provider.requests) == 2
    assert result.error == (
        "Agent loop reached max_iterations (2) without a final_answer"
    )
    assert events.list_persisted_events()[-1].metadata == {
        "session_id": "loop-session-1",
        "status": "failed",
        "error": result.error,
        "iterations_used": 2,
    }
    second_messages = provider.requests[1].messages
    assert [
        (message.role, message.content) for message in second_messages
    ] == [
        (ProviderMessageRole.SYSTEM, AGENT_LOOP_SYSTEM_PROMPT),
        (ProviderMessageRole.USER, "Produce an answer"),
        (
            ProviderMessageRole.ASSISTANT,
            tool_output("observe", {"message": "First observation"}),
        ),
        (ProviderMessageRole.USER, "First observation"),
    ]


def test_loop_accumulates_context_for_each_provider_invocation(
    tmp_path,
) -> None:
    outputs = [
        tool_output("observe", {"message": "First observation"}),
        tool_output("observe", {"message": "Second observation"}),
        tool_output("final_answer", {"answer": "Done."}),
    ]
    loop, provider, _ = service(tmp_path, outputs)

    result = loop.run(request(max_iterations=3))

    assert result.status == AgentLoopStatus.COMPLETED
    assert [
        (message.role, message.content)
        for message in provider.requests[2].messages
    ] == [
        (ProviderMessageRole.SYSTEM, AGENT_LOOP_SYSTEM_PROMPT),
        (ProviderMessageRole.USER, "Produce an answer"),
        (ProviderMessageRole.ASSISTANT, outputs[0]),
        (ProviderMessageRole.USER, "First observation"),
        (ProviderMessageRole.ASSISTANT, outputs[1]),
        (ProviderMessageRole.USER, "Second observation"),
    ]
