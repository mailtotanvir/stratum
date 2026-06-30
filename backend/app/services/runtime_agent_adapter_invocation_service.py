from typing import Any

from app.models.agent_invocation_lifecycle import (
    AgentInvocationRecord,
)
from app.models.runtime_event import RuntimeEvent
from app.services.agent_event_bridge_service import (
    AgentEventBridgeService,
    agent_event_bridge_service,
)
from app.services.agent_invocation_service import (
    AgentInvocationService,
    agent_invocation_service,
)


class RuntimeAgentAdapterInvocationService:
    def __init__(
        self,
        invocations: AgentInvocationService | None = None,
        event_bridge: AgentEventBridgeService | None = None,
    ) -> None:
        self._invocations = invocations or agent_invocation_service
        self._event_bridge = event_bridge or agent_event_bridge_service

    def request_invocation(
        self,
        *,
        adapter_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationRecord:
        return self._invocations.start_invocation(
            adapter_id=adapter_id,
            capability_id=capability_id,
            metadata=metadata,
        )

    def normalize_adapter_event(
        self,
        invocation_id: str,
        *,
        source_event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> AgentInvocationRecord:
        return self._invocations.normalize_external_event(
            invocation_id,
            source_event_type=source_event_type,
            message=message,
            metadata=metadata,
            severity=severity,
        )

    def canonical_runtime_event_payloads(
        self,
        invocation_id: str,
    ) -> list[dict[str, Any]]:
        return self._invocations.canonical_event_payloads(invocation_id)

    def materialize_runtime_events(
        self,
        invocation_id: str,
    ) -> list[RuntimeEvent]:
        record = self._invocations.get_invocation(invocation_id)
        return [
            self._event_bridge.to_runtime_event(
                event_id=index,
                source_event_type=_canonical_source_event_type(event),
                message=event.message,
                metadata={
                    "agent_invocation_id": record.invocation_id,
                    "adapter_id": record.adapter_id,
                    "capability_id": record.capability_id,
                    "runtime_session_id": record.runtime_session_id,
                    "state": event.state.value,
                    **dict(event.metadata),
                },
                timestamp=event.timestamp.isoformat(),
            )
            for index, event in enumerate(record.history, start=1)
        ]


runtime_agent_adapter_invocation_service = (
    RuntimeAgentAdapterInvocationService()
)


def _canonical_source_event_type(event) -> str:
    if event.source_event_type:
        return event.source_event_type
    lifecycle_to_source = {
        "created": "started",
        "accepted": "started",
        "running": "started",
        "waiting_for_approval": "approval_requested",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }
    return lifecycle_to_source.get(event.event_type.value, event.event_type.value)
