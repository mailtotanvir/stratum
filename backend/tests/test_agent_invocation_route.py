from app.models.agent_invocation_lifecycle import AgentInvocationLifecycleState
from app.routes.agent_invocation import (
    AgentInvocationCreateRequest,
    AgentInvocationCancelRequest,
    cancel_agent_invocation,
    create_agent_invocation,
    get_agent_invocation_history,
    get_agent_invocation_status,
    list_agent_invocations,
)


def test_create_agent_invocation_starts_simulated_lifecycle() -> None:
    record = create_agent_invocation(
        AgentInvocationCreateRequest(
            adapter_id="agent-fake",
            capability_id="tool_use",
            metadata={
                "source": "agent-invocation-route-test",
                "runtime_session_id": "runtime-session-1",
            },
        )
    )

    assert record.adapter_id == "agent-fake"
    assert record.capability_id == "tool_use"
    assert record.runtime_session_id == "runtime-session-1"
    assert record.state == AgentInvocationLifecycleState.RUNNING
    assert [event.state for event in record.history] == [
        AgentInvocationLifecycleState.CREATED,
        AgentInvocationLifecycleState.ACCEPTED,
        AgentInvocationLifecycleState.RUNNING,
    ]


def test_list_agent_invocations_returns_recent_invocations() -> None:
    first = create_agent_invocation(
        AgentInvocationCreateRequest(
            adapter_id="agent-fake",
            capability_id="memory",
            metadata={"source": "agent-invocation-route-test"},
        )
    )
    second = create_agent_invocation(
        AgentInvocationCreateRequest(
            adapter_id="agent-fake",
            capability_id="tool_use",
            metadata={"source": "agent-invocation-route-test"},
        )
    )

    response = list_agent_invocations(limit=1)

    assert len(response.invocations) == 1
    assert response.invocations[0].invocation_id == second.invocation_id
    assert first.invocation_id != second.invocation_id


def test_get_agent_invocation_status_returns_summary() -> None:
    created = create_agent_invocation(
        AgentInvocationCreateRequest(
            adapter_id="agent-fake",
            capability_id="tool_use",
            metadata={"source": "agent-invocation-route-test"},
        )
    )

    body = get_agent_invocation_status(created.invocation_id)

    assert body.invocation_id == created.invocation_id
    assert body.state == AgentInvocationLifecycleState.RUNNING
    assert body.history_length == 3
    assert body.runtime_session_id is None


def test_get_agent_invocation_history_returns_event_summary() -> None:
    created = create_agent_invocation(
        AgentInvocationCreateRequest(
            adapter_id="agent-fake",
            capability_id="tool_use",
            metadata={"source": "agent-invocation-route-test"},
        )
    )

    body = get_agent_invocation_history(created.invocation_id)

    assert body.invocation_id == created.invocation_id
    assert body.adapter_id == created.adapter_id
    assert body.capability_id == created.capability_id
    assert body.states == [
        AgentInvocationLifecycleState.CREATED,
        AgentInvocationLifecycleState.ACCEPTED,
        AgentInvocationLifecycleState.RUNNING,
    ]
    assert len(body.events) == 3


def test_create_agent_invocation_rejects_invalid_capability() -> None:
    try:
        create_agent_invocation(
            AgentInvocationCreateRequest(
                adapter_id="agent-fake",
                capability_id="missing",
                metadata={},
            )
        )
    except Exception as exc:
        assert "Capability is not supported" in str(exc)
    else:
        raise AssertionError("Expected exception")


def test_create_agent_invocation_rejects_invalid_adapter() -> None:
    try:
        create_agent_invocation(
            AgentInvocationCreateRequest(
                adapter_id="missing",
                capability_id="tool_use",
                metadata={},
            )
        )
    except Exception as exc:
        assert "Agent adapter is not registered" in str(exc)
    else:
        raise AssertionError("Expected exception")


def test_cancel_agent_invocation_transitions_to_cancelled() -> None:
    created = create_agent_invocation(
        AgentInvocationCreateRequest(
            adapter_id="agent-fake",
            capability_id="tool_use",
            metadata={"source": "agent-invocation-route-test"},
        )
    )

    body = cancel_agent_invocation(
        created.invocation_id,
        AgentInvocationCancelRequest(
            message="Stop invocation",
            metadata={"reason": "test"},
        ),
    )

    assert body.state == AgentInvocationLifecycleState.CANCELLED
    assert body.history[-1].state == AgentInvocationLifecycleState.CANCELLED
