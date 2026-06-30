from app.models.runtime_event import EventType, Severity
from app.services.agent_event_bridge_service import AgentEventBridgeService


def test_event_bridge_maps_known_event_types() -> None:
    bridge = AgentEventBridgeService()

    event = bridge.normalize(
        source_event_type="tool_completed",
        message="Tool completed",
        metadata={"tool": "write_file"},
        severity=Severity.WARNING,
    )

    assert event.source_event_type == "tool_completed"
    assert event.runtime_event_type == EventType.AGENT_LOOP_TOOL_COMPLETED.value
    assert event.severity == Severity.WARNING.value
    assert event.metadata == {"tool": "write_file"}


def test_event_bridge_uses_safe_fallback_for_unknown_events() -> None:
    bridge = AgentEventBridgeService()

    event = bridge.normalize(
        source_event_type="external_update",
        message="External update",
    )

    assert event.runtime_event_type == EventType.RUNTIME_TASK_STARTED.value


def test_event_bridge_can_materialize_runtime_events() -> None:
    bridge = AgentEventBridgeService()

    event = bridge.to_runtime_event(
        event_id=7,
        source_event_type="approval_requested",
        message="Approval requested",
        metadata={"approval_id": "approval-1"},
        timestamp="2026-06-30T12:00:00+00:00",
    )

    assert event.id == 7
    assert event.type == EventType.AGENT_LOOP_APPROVAL_REQUESTED
    assert event.metadata["source_event_type"] == "approval_requested"
    assert event.metadata["runtime_event_type"] == "agent_loop_approval_requested"
