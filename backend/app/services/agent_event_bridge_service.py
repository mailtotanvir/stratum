from app.models.agent_adapter import AgentEventBridgeEvent
from app.models.runtime_event import EventType, Severity
from app.models.runtime_event import RuntimeEvent
from datetime import UTC, datetime


class AgentEventBridgeService:
    _event_type_map = {
        "started": EventType.AGENT_EXECUTION_STARTED,
        "step_observed": EventType.AGENT_LOOP_TOOL_SELECTED,
        "completed": EventType.AGENT_EXECUTION_COMPLETED,
        "failed": EventType.AGENT_EXECUTION_FAILED,
        "cancelled": EventType.AGENT_LOOP_STOPPED,
        "approval_requested": EventType.AGENT_LOOP_APPROVAL_REQUESTED,
        "approval_responded": EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        "approval_resumed": EventType.AGENT_LOOP_APPROVAL_RESUMED,
        "tool_selected": EventType.AGENT_LOOP_TOOL_SELECTED,
        "tool_completed": EventType.AGENT_LOOP_TOOL_COMPLETED,
        "observation": EventType.TOOL_RESULT,
        "artifact_declared": EventType.ARTIFACT_CREATED,
        "action": EventType.TOOL_CALL,
        "warning": EventType.WARNING,
        "error": EventType.ERROR,
    }

    def normalize(
        self,
        *,
        source_event_type: str,
        message: str,
        metadata: dict | None = None,
        severity: Severity | str = Severity.INFO,
    ) -> AgentEventBridgeEvent:
        runtime_event_type = self._event_type_map.get(
            source_event_type,
            EventType.RUNTIME_TASK_STARTED,
        )
        severity_value = severity.value if isinstance(severity, Severity) else severity
        return AgentEventBridgeEvent(
            source_event_type=source_event_type,
            runtime_event_type=runtime_event_type.value,
            message=message,
            severity=severity_value,
            metadata=dict(metadata or {}),
        )

    def to_runtime_event(
        self,
        *,
        event_id: int,
        source_event_type: str,
        message: str,
        metadata: dict | None = None,
        severity: Severity | str = Severity.INFO,
        timestamp: str | None = None,
    ) -> RuntimeEvent:
        bridge_event = self.normalize(
            source_event_type=source_event_type,
            message=message,
            metadata=metadata,
            severity=severity,
        )
        return RuntimeEvent(
            id=event_id,
            ts=timestamp or datetime.now(UTC).isoformat(),
            type=EventType(bridge_event.runtime_event_type),
            severity=Severity(bridge_event.severity),
            message=bridge_event.message,
            metadata=bridge_event.model_dump(mode="json", exclude={"message"}),
        )


agent_event_bridge_service = AgentEventBridgeService()
