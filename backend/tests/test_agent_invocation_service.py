from app.models.agent_adapter import AgentCapabilityManifest
from app.models.agent_invocation_lifecycle import AgentInvocationLifecycleState
from app.services.agent_adapter_registry_service import AgentAdapterRegistryService
from app.services.agent_invocation_service import AgentInvocationService


class _Adapter:
    def __init__(self, adapter_id: str, capabilities: list[str]) -> None:
        self.adapter_id = adapter_id
        self.manifest = AgentCapabilityManifest(
            adapter_id=adapter_id,
            display_name=adapter_id,
            supported_capabilities=capabilities,
            supported_agent_types=["coding"],
        )


def test_create_invocation_records_initial_history() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService([
            _Adapter("agent-a", ["plan", "act"])
        ])
    )

    record = service.create_invocation(
        adapter_id="agent-a",
        capability_id="plan",
        metadata={"task_id": "task-1", "runtime_session_id": "session-1"},
    )

    assert record.adapter_id == "agent-a"
    assert record.capability_id == "plan"
    assert record.runtime_session_id == "session-1"
    assert record.state == AgentInvocationLifecycleState.CREATED
    assert record.history[0].state == AgentInvocationLifecycleState.CREATED


def test_create_invocation_rejects_unknown_adapter() -> None:
    service = AgentInvocationService(adapter_registry=AgentAdapterRegistryService())

    try:
        service.create_invocation(adapter_id="missing", capability_id="plan")
    except ValueError as exc:
        assert "Agent adapter is not registered" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_create_invocation_rejects_unknown_capability() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService([
            _Adapter("agent-a", ["plan"])
        ])
    )

    try:
        service.create_invocation(adapter_id="agent-a", capability_id="act")
    except ValueError as exc:
        assert "Capability is not supported" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_state_transitions_and_external_normalization() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService([
            _Adapter("agent-a", ["plan"])
        ])
    )
    record = service.create_invocation(adapter_id="agent-a", capability_id="plan")
    record = service.transition(
        record.invocation_id,
        AgentInvocationLifecycleState.ACCEPTED,
        message="Accepted",
    )
    record = service.normalize_external_event(
        record.invocation_id,
        source_event_type="approval_requested",
        message="Approval requested",
        metadata={"approval_id": "approval-1"},
    )

    assert record.state == AgentInvocationLifecycleState.WAITING_FOR_APPROVAL
    assert record.history[-1].source_event_type == "approval_requested"


def test_status_and_history_summaries_reflect_latest_event() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService([
            _Adapter("agent-a", ["plan"])
        ])
    )
    record = service.create_invocation(adapter_id="agent-a", capability_id="plan")
    record = service.transition(
        record.invocation_id,
        AgentInvocationLifecycleState.RUNNING,
        message="Running",
    )

    summary = service.status_summary(record.invocation_id)
    history = service.history_summary(record.invocation_id)
    payloads = service.canonical_event_payloads(record.invocation_id)

    assert summary.state == AgentInvocationLifecycleState.RUNNING
    assert summary.history_length == 2
    assert summary.runtime_session_id is None
    assert history.states[-1] == AgentInvocationLifecycleState.RUNNING
    assert payloads[-1]["metadata"]["agent_invocation_id"] == record.invocation_id


def test_recent_invocations_are_returned_newest_first() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService(
            [_Adapter("agent-a", ["plan", "act"])]
        )
    )
    first = service.create_invocation(adapter_id="agent-a", capability_id="plan")
    second = service.create_invocation(adapter_id="agent-a", capability_id="act")

    recent = service.list_recent_invocations(limit=1)

    assert [record.invocation_id for record in recent] == [second.invocation_id]
    assert first.invocation_id != second.invocation_id


def test_cancel_invocation_adds_cancelled_state() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService(
            [_Adapter("agent-a", ["plan"])]
        )
    )
    record = service.start_invocation(adapter_id="agent-a", capability_id="plan")

    cancelled = service.cancel_invocation(record.invocation_id)

    assert cancelled.state == AgentInvocationLifecycleState.CANCELLED
    assert cancelled.history[-1].state == AgentInvocationLifecycleState.CANCELLED


def test_mock_external_adapter_invocation_replays_normalized_history() -> None:
    service = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService(
            [
                _Adapter(
                    "agent-mock-external",
                    ["plan", "observe", "approve", "artifact"],
                )
            ]
        )
    )

    record = service.start_invocation(
        adapter_id="agent-mock-external",
        capability_id="plan",
        metadata={
            "runtime_session_id": "session-mock-1",
            "user_request": "Demo mock invocation",
        },
    )

    history = service.history_summary(record.invocation_id)

    assert record.state == AgentInvocationLifecycleState.COMPLETED
    assert history.states[:3] == [
        AgentInvocationLifecycleState.CREATED,
        AgentInvocationLifecycleState.ACCEPTED,
        AgentInvocationLifecycleState.RUNNING,
    ]
    assert history.events[-2].source_event_type == "artifact_declared"
    assert history.events[-2].metadata["artifact_path"] == (
        f"artifacts/{record.invocation_id}/summary.md"
    )
    assert history.events[-2].metadata["writes_workspace_directly"] is False
    assert history.events[-1].state == AgentInvocationLifecycleState.COMPLETED
    assert history.events[-1].metadata["adapter_result"]["invocation_id"] == record.invocation_id
    payloads = service.canonical_event_payloads(record.invocation_id)
    assert payloads[-2]["type"] == "artifact_created"
    assert payloads[-1]["type"] == "agent_execution_completed"
