from app.models.agent_adapter import AgentCapabilityManifest
from app.models.agent_invocation_lifecycle import (
    AgentInvocationLifecycleState,
)
from app.services.agent_adapter_registry_service import (
    AgentAdapterRegistryService,
)
from app.services.agent_invocation_service import AgentInvocationService
from app.services.runtime_agent_adapter_invocation_service import (
    RuntimeAgentAdapterInvocationService,
)


class _Adapter:
    def __init__(self, adapter_id: str, capabilities: list[str]) -> None:
        self.adapter_id = adapter_id
        self.manifest = AgentCapabilityManifest(
            adapter_id=adapter_id,
            display_name=adapter_id,
            supported_capabilities=capabilities,
            supported_agent_types=["coding"],
        )
        self.execute_calls = 0

    def execute(self) -> None:
        self.execute_calls += 1


def test_valid_adapter_capability_request_creates_invocation() -> None:
    adapter = _Adapter("agent-a", ["plan", "act"])
    invocations = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService([adapter])
    )
    seam = RuntimeAgentAdapterInvocationService(invocations=invocations)

    record = seam.request_invocation(
        adapter_id="agent-a",
        capability_id="plan",
        metadata={"source": "runtime-loop", "runtime_session_id": "session-7"},
    )

    assert record.adapter_id == "agent-a"
    assert record.capability_id == "plan"
    assert record.state == AgentInvocationLifecycleState.RUNNING
    assert record.metadata == {
        "source": "runtime-loop",
        "runtime_session_id": "session-7",
    }
    assert record.runtime_session_id == "session-7"
    assert adapter.execute_calls == 0


def test_invalid_adapter_or_capability_is_rejected() -> None:
    invocations = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService(
            [_Adapter("agent-a", ["plan"])]
        )
    )
    seam = RuntimeAgentAdapterInvocationService(invocations=invocations)

    try:
        seam.request_invocation(adapter_id="missing", capability_id="plan")
    except ValueError as exc:
        assert "Agent adapter is not registered" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        seam.request_invocation(adapter_id="agent-a", capability_id="act")
    except ValueError as exc:
        assert "Capability is not supported" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_event_normalization_produces_canonical_payloads() -> None:
    invocations = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService(
            [_Adapter("agent-a", ["plan"])]
        )
    )
    seam = RuntimeAgentAdapterInvocationService(invocations=invocations)
    record = seam.request_invocation(adapter_id="agent-a", capability_id="plan")

    normalized = seam.normalize_adapter_event(
        record.invocation_id,
        source_event_type="approval_requested",
        message="Approval requested",
        metadata={"approval_id": "approval-1"},
    )
    payloads = seam.canonical_runtime_event_payloads(record.invocation_id)

    assert normalized.state == AgentInvocationLifecycleState.WAITING_FOR_APPROVAL
    assert payloads[-1]["type"] == "agent_loop_approval_requested"
    assert payloads[-1]["metadata"]["agent_invocation_id"] == record.invocation_id
    assert payloads[-1]["metadata"]["approval_id"] == "approval-1"
    assert payloads[-1]["metadata"]["runtime_session_id"] is None


def test_cancellation_and_failure_propagation_remain_stratum_owned() -> None:
    invocations = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService(
            [_Adapter("agent-a", ["plan"])]
        )
    )
    seam = RuntimeAgentAdapterInvocationService(invocations=invocations)
    record = seam.request_invocation(adapter_id="agent-a", capability_id="plan")

    failed = invocations.transition(
        record.invocation_id,
        AgentInvocationLifecycleState.FAILED,
        message="Adapter failure",
    )

    assert failed.state == AgentInvocationLifecycleState.FAILED

    try:
        invocations.cancel_invocation(record.invocation_id)
    except ValueError as exc:
        assert "cannot be cancelled" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_runtime_seam_does_not_call_external_adapter_execution() -> None:
    adapter = _Adapter("agent-a", ["plan"])
    invocations = AgentInvocationService(
        adapter_registry=AgentAdapterRegistryService([adapter])
    )
    seam = RuntimeAgentAdapterInvocationService(invocations=invocations)

    seam.request_invocation(adapter_id="agent-a", capability_id="plan")
    seam.materialize_runtime_events(
        seam.request_invocation(adapter_id="agent-a", capability_id="plan").invocation_id
    )

    assert adapter.execute_calls == 0
