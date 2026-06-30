import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.models.agent_adapter import AgentCapabilityManifest
from app.models.agent_invocation_lifecycle import (
    AgentInvocationHistorySummary,
    AgentInvocationLifecycleEvent,
    AgentInvocationLifecycleEventType,
    AgentInvocationLifecycleState,
    AgentInvocationRecord,
    AgentInvocationSummary,
)
from app.models.runtime_event import EventType, Severity
from app.services.agent_adapter_registry_service import (
    AgentAdapterRegistryService,
)
from app.services.agent_adapter_catalog_service import agent_adapter_catalog_service
from app.services.agent_event_bridge_service import (
    AgentEventBridgeService,
    agent_event_bridge_service,
)
from app.services.mock_external_agent_adapter import MockExternalAgentAdapter


class AgentInvocationService:
    def __init__(
        self,
        adapter_registry: AgentAdapterRegistryService | None = None,
        event_bridge: AgentEventBridgeService | None = None,
    ) -> None:
        self._adapter_registry = (
            adapter_registry or agent_adapter_catalog_service.registry
        )
        self._event_bridge = event_bridge or agent_event_bridge_service
        self._records: dict[str, AgentInvocationRecord] = {}

    def reset(self) -> None:
        self._records.clear()

    def create_invocation(
        self,
        *,
        adapter_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationRecord:
        adapter = self._resolve_adapter(adapter_id)
        self._validate_capability(adapter.manifest, capability_id)
        created_at = datetime.now(UTC)
        runtime_session_id = _runtime_session_id(metadata or {})
        invocation_id = _invocation_id(adapter_id=adapter_id, capability_id=capability_id, metadata=metadata or {})
        record = AgentInvocationRecord(
            invocation_id=invocation_id,
            adapter_id=adapter_id,
            capability_id=capability_id,
            runtime_session_id=runtime_session_id,
            state=AgentInvocationLifecycleState.CREATED,
            created_at=created_at,
            updated_at=created_at,
            history=[
                self._make_event(
                    event_type=AgentInvocationLifecycleEventType.CREATED,
                    state=AgentInvocationLifecycleState.CREATED,
                    message="Agent invocation created",
                    metadata=metadata or {},
                    timestamp=created_at,
                )
            ],
            metadata=dict(metadata or {}),
        )
        self._records[record.invocation_id] = record
        return record

    def start_invocation(
        self,
        *,
        adapter_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationRecord:
        record = self.create_invocation(
            adapter_id=adapter_id,
            capability_id=capability_id,
            metadata=metadata,
        )
        record = self.transition(
            record.invocation_id,
            AgentInvocationLifecycleState.ACCEPTED,
            message="Agent invocation accepted",
            metadata=dict(metadata or {}),
        )
        record = self.transition(
            record.invocation_id,
            AgentInvocationLifecycleState.RUNNING,
            message="Agent invocation running",
            metadata=dict(metadata or {}),
        )
        if adapter_id == MockExternalAgentAdapter.adapter_id:
            record = self._simulate_mock_external_invocation(
                record.invocation_id,
                capability_id=capability_id,
                metadata=dict(metadata or {}),
            )
        return record

    def transition(
        self,
        invocation_id: str,
        state: AgentInvocationLifecycleState,
        *,
        message: str,
        metadata: dict[str, Any] | None = None,
        source_event_type: str | None = None,
    ) -> AgentInvocationRecord:
        record = self.get_invocation(invocation_id)
        timestamp = datetime.now(UTC)
        updated = record.model_copy(
            update={
                "state": state,
                "updated_at": timestamp,
                "history": record.history
                + [
                    self._make_event(
                        event_type=_event_type_for_state(state),
                        state=state,
                        message=message,
                        metadata=metadata or {},
                        timestamp=timestamp,
                        source_event_type=source_event_type,
                    )
                ],
            },
            deep=True,
        )
        self._records[invocation_id] = updated
        return updated

    def cancel_invocation(
        self,
        invocation_id: str,
        *,
        message: str = "Agent invocation cancelled",
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationRecord:
        record = self.get_invocation(invocation_id)
        if record.state in {
            AgentInvocationLifecycleState.COMPLETED,
            AgentInvocationLifecycleState.FAILED,
            AgentInvocationLifecycleState.CANCELLED,
        }:
            raise ValueError(
                f"Agent invocation cannot be cancelled from state {record.state.value}: {invocation_id}"
            )
        return self.transition(
            invocation_id,
            AgentInvocationLifecycleState.CANCELLED,
            message=message,
            metadata=metadata or {},
        )

    def normalize_external_event(
        self,
        invocation_id: str,
        *,
        source_event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        severity: Severity | str = Severity.INFO,
    ) -> AgentInvocationRecord:
        record = self.get_invocation(invocation_id)
        bridge_event = self._event_bridge.normalize(
            source_event_type=source_event_type,
            message=message,
            metadata=metadata,
            severity=severity,
        )
        event_state = _state_for_runtime_event_type(bridge_event.runtime_event_type)
        next_state = event_state or record.state
        return self.transition(
            invocation_id,
            next_state,
            message=bridge_event.message,
            metadata={
                "source_event_type": bridge_event.source_event_type,
                "runtime_event_type": bridge_event.runtime_event_type,
                "severity": bridge_event.severity,
                **dict(bridge_event.metadata),
            },
            source_event_type=bridge_event.source_event_type,
        )

    def get_invocation(self, invocation_id: str) -> AgentInvocationRecord:
        try:
            return self._records[invocation_id]
        except KeyError as exc:
            raise ValueError(f"Agent invocation is not registered: {invocation_id}") from exc

    def list_invocations(self) -> list[AgentInvocationRecord]:
        return [self._records[invocation_id] for invocation_id in sorted(self._records)]

    def list_recent_invocations(self, limit: int = 20) -> list[AgentInvocationRecord]:
        recent = sorted(
            self._records.values(),
            key=lambda record: (record.updated_at, record.invocation_id),
            reverse=True,
        )
        return recent[:limit]

    def status_summary(self, invocation_id: str) -> AgentInvocationSummary:
        record = self.get_invocation(invocation_id)
        last_event = record.history[-1] if record.history else None
        return AgentInvocationSummary(
            invocation_id=record.invocation_id,
            adapter_id=record.adapter_id,
            capability_id=record.capability_id,
            runtime_session_id=record.runtime_session_id,
            state=record.state,
            history_length=len(record.history),
            last_event_type=last_event.event_type if last_event else None,
            last_message=last_event.message if last_event else None,
            metadata=dict(record.metadata),
        )

    def history_summary(self, invocation_id: str) -> AgentInvocationHistorySummary:
        record = self.get_invocation(invocation_id)
        return AgentInvocationHistorySummary(
            invocation_id=record.invocation_id,
            adapter_id=record.adapter_id,
            capability_id=record.capability_id,
            runtime_session_id=record.runtime_session_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            states=[event.state for event in record.history],
            events=list(record.history),
        )

    def canonical_event_payloads(self, invocation_id: str) -> list[dict[str, Any]]:
        record = self.get_invocation(invocation_id)
        payloads: list[dict[str, Any]] = []
        for index, event in enumerate(record.history, start=1):
            source_event_type = event.source_event_type or event.event_type.value
            runtime_event = self._event_bridge.to_runtime_event(
                event_id=index,
                source_event_type=source_event_type,
                message=event.message,
                metadata={
                    "agent_invocation_id": record.invocation_id,
                    "adapter_id": record.adapter_id,
                    "capability_id": record.capability_id,
                    "runtime_session_id": record.runtime_session_id,
                    "state": event.state.value,
                    **dict(event.metadata),
                },
                severity=Severity.INFO,
                timestamp=event.timestamp.isoformat(),
            )
            payloads.append(runtime_event.model_dump(mode="json"))
            payloads[-1]["metadata"] = {
                "agent_invocation_id": record.invocation_id,
                "adapter_id": record.adapter_id,
                "capability_id": record.capability_id,
                "runtime_session_id": record.runtime_session_id,
                "state": event.state.value,
                **dict(event.metadata),
                **payloads[-1]["metadata"],
            }
        return payloads

    def _resolve_adapter(self, adapter_id: str):
        return self._adapter_registry.get_adapter(adapter_id)

    def _validate_capability(
        self, manifest: AgentCapabilityManifest, capability_id: str
    ) -> None:
        if capability_id not in manifest.supported_capabilities:
            raise ValueError(
                f"Capability is not supported by adapter {manifest.adapter_id}: {capability_id}"
            )

    def _make_event(
        self,
        *,
        event_type: AgentInvocationLifecycleEventType,
        state: AgentInvocationLifecycleState,
        message: str,
        metadata: dict[str, Any],
        timestamp: datetime,
        source_event_type: str | None = None,
    ) -> AgentInvocationLifecycleEvent:
        return AgentInvocationLifecycleEvent(
            event_type=event_type,
            state=state,
            message=message,
            timestamp=timestamp,
            source_event_type=source_event_type,
            metadata=dict(metadata),
        )

    def _simulate_mock_external_invocation(
        self,
        invocation_id: str,
        *,
        capability_id: str,
        metadata: dict[str, Any],
    ) -> AgentInvocationRecord:
        adapter = MockExternalAgentAdapter()
        result = adapter.invoke(
            capability_id=capability_id,
            invocation_id=invocation_id,
            user_request=str(metadata.get("user_request", "Mock invocation")),
            metadata=metadata,
        )
        record = self.get_invocation(invocation_id)
        for event in adapter.emit_events(
            invocation_id=invocation_id,
            capability_id=capability_id,
            metadata=metadata,
        ):
            event_metadata = dict(event.get("metadata") or {})
            if event["source_event_type"] in {"completed", "failed", "cancelled"}:
                event_metadata["adapter_result"] = result.model_dump(mode="json")
            record = self.normalize_external_event(
                invocation_id,
                source_event_type=event["source_event_type"],
                message=event["message"],
                metadata=event_metadata,
            )
        terminal_state = {
            "completed": AgentInvocationLifecycleState.COMPLETED,
            "failed": AgentInvocationLifecycleState.FAILED,
            "cancelled": AgentInvocationLifecycleState.CANCELLED,
        }[result.status]
        if record.state != terminal_state:
            record = self.transition(
                invocation_id,
                terminal_state,
                message=result.summary or "Mock external agent finished",
                metadata={
                    "adapter_result": result.model_dump(mode="json"),
                    "invocation_id": invocation_id,
                },
            )
        return record


def _invocation_id(
    *,
    adapter_id: str,
    capability_id: str,
    metadata: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "adapter_id": adapter_id,
            "capability_id": capability_id,
            "metadata": metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"agent-invocation-{digest}"


def _runtime_session_id(metadata: dict[str, Any]) -> str | None:
    session_id = metadata.get("runtime_session_id") or metadata.get("session_id")
    if session_id is None:
        return None
    return str(session_id)


def _event_type_for_state(
    state: AgentInvocationLifecycleState,
) -> AgentInvocationLifecycleEventType:
    return {
        AgentInvocationLifecycleState.CREATED: AgentInvocationLifecycleEventType.CREATED,
        AgentInvocationLifecycleState.ACCEPTED: AgentInvocationLifecycleEventType.ACCEPTED,
        AgentInvocationLifecycleState.RUNNING: AgentInvocationLifecycleEventType.RUNNING,
        AgentInvocationLifecycleState.WAITING_FOR_APPROVAL: AgentInvocationLifecycleEventType.WAITING_FOR_APPROVAL,
        AgentInvocationLifecycleState.COMPLETED: AgentInvocationLifecycleEventType.COMPLETED,
        AgentInvocationLifecycleState.FAILED: AgentInvocationLifecycleEventType.FAILED,
        AgentInvocationLifecycleState.CANCELLED: AgentInvocationLifecycleEventType.CANCELLED,
    }[state]


def _state_for_runtime_event_type(
    runtime_event_type: str,
) -> AgentInvocationLifecycleState | None:
    return {
        EventType.AGENT_EXECUTION_STARTED.value: AgentInvocationLifecycleState.RUNNING,
        EventType.AGENT_EXECUTION_COMPLETED.value: AgentInvocationLifecycleState.COMPLETED,
        EventType.AGENT_EXECUTION_FAILED.value: AgentInvocationLifecycleState.FAILED,
        EventType.AGENT_LOOP_APPROVAL_REQUESTED.value: AgentInvocationLifecycleState.WAITING_FOR_APPROVAL,
        EventType.AGENT_LOOP_APPROVAL_RESPONDED.value: AgentInvocationLifecycleState.ACCEPTED,
        EventType.AGENT_LOOP_APPROVAL_RESUMED.value: AgentInvocationLifecycleState.RUNNING,
        EventType.AGENT_LOOP_FAILED.value: AgentInvocationLifecycleState.FAILED,
        EventType.AGENT_LOOP_COMPLETED.value: AgentInvocationLifecycleState.COMPLETED,
    }.get(runtime_event_type)


agent_invocation_service = AgentInvocationService()
