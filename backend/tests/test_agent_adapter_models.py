import pytest
from pydantic import ValidationError

from app.models.agent_adapter import (
    AgentAdapterTransport,
    AgentCapabilityManifest,
    AgentEventBridgeEvent,
    AgentInvocation,
    AgentInvocationResult,
)


def test_capability_manifest_normalizes_lists() -> None:
    manifest = AgentCapabilityManifest(
        adapter_id="agent-hosted",
        display_name="Hosted Agent",
        supported_agent_types=["coding", "coding", "research"],
        supported_capabilities=["tool_use", "tool_use", "memory"],
        supported_modalities=["text", "text", "files"],
        transport=AgentAdapterTransport.HOSTED,
    )

    assert manifest.supported_agent_types == ["coding", "research"]
    assert manifest.supported_capabilities == ["tool_use", "memory"]
    assert manifest.supported_modalities == ["text", "files"]


def test_capability_manifest_rejects_blank_identifiers() -> None:
    with pytest.raises(ValidationError):
        AgentCapabilityManifest(adapter_id=" ", display_name="Agent")


def test_invocation_normalizes_capabilities() -> None:
    invocation = AgentInvocation(
        adapter_id="agent-a2a",
        invocation_id="inv-1",
        user_request="Investigate the incident",
        capabilities=["plan", "plan", "act"],
    )

    assert invocation.capabilities == ["plan", "act"]


def test_invocation_result_validates_required_identity_fields() -> None:
    with pytest.raises(ValidationError):
        AgentInvocationResult(
            invocation_id="inv-1",
            adapter_id="adapter-1",
            status="completed",
            error_message=" ",
        )


def test_event_bridge_model_is_stable() -> None:
    event = AgentEventBridgeEvent(
        source_event_type="tool_completed",
        runtime_event_type="agent_loop_tool_completed",
        message="Tool completed",
        metadata={"tool": "write_file"},
    )

    assert event.runtime_event_type == "agent_loop_tool_completed"
    assert event.metadata == {"tool": "write_file"}
