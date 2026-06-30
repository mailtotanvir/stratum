from __future__ import annotations

from app.services.agent_adapter_contract_harness import (
    AgentAdapterContractHarness,
)
from app.services.mock_external_agent_adapter import MockExternalAgentAdapter


def test_mock_external_agent_adapter_passes_contract_harness() -> None:
    adapter = MockExternalAgentAdapter()
    result = AgentAdapterContractHarness().validate(
        adapter,
        capability_id="plan",
        metadata={
            "runtime_session_id": "session-42",
            "approval_required": True,
        },
    )

    assert result.manifest.adapter_id == "agent-mock-external"
    assert result.manifest.transport.value == "hosted"
    assert result.invocation_result.status == "completed"
    assert result.invocation_result.metadata["demo_only"] is True
    assert [event.source_event_type for event in result.normalized_events] == [
        "started",
        "step_observed",
        "approval_requested",
        "artifact_declared",
        "completed",
    ]
    assert [
        event.runtime_event_type for event in result.normalized_events
    ] == [
        "agent_execution_started",
        "agent_loop_tool_selected",
        "agent_loop_approval_requested",
        "artifact_created",
        "agent_execution_completed",
    ]
    assert result.declared_artifacts[0]["writes_workspace_directly"] is False
    assert result.cancellation_supported is True
    assert adapter.cancelled_invocations == ["invocation-1"]


def test_mock_external_agent_adapter_can_emit_failure_and_cancellation_paths() -> None:
    adapter = MockExternalAgentAdapter()

    failed_result = adapter.invoke(
        capability_id="observe",
        invocation_id="invocation-failed",
        user_request="Inspect a failure path",
        metadata={"outcome": "failed"},
    )
    cancelled_events = adapter.emit_events(
        invocation_id="invocation-cancelled",
        capability_id="approve",
        metadata={"outcome": "cancelled"},
    )

    assert failed_result.status == "failed"
    assert failed_result.error_type == "mock_external_agent_failure"
    assert failed_result.artifacts[0]["path"] == (
        "artifacts/invocation-failed/summary.md"
    )
    assert cancelled_events[-1]["source_event_type"] == "cancelled"
