from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.models.agent_adapter import AgentCapabilityManifest
from app.models.execution_participant import (
    ExecutionCapabilityRouteRequest,
    ExecutionCapabilityManifest,
    ExecutionInvocation,
    ExecutionInvocationState,
    ExecutionParticipantContract,
    ExecutionParticipant,
    ExecutionParticipantCapability,
    ExecutionParticipantHealth,
    ExecutionParticipantKind,
    ExecutionParticipantLifecycle,
    ExecutionParticipantRegistry,
    ExecutionParticipantRegistryDiagnostics,
    ExecutionRiskLevel,
)
from app.models.runtime_event import EventType, Severity
from app.services.agent_adapter_catalog_service import agent_adapter_catalog_service
from app.services.event_service import EventService, event_service
from app.services.tool_registry_service import tool_registry_service
from app.providers.provider_registry import provider_registry


class ExecutionParticipantRegistryService:
    def __init__(self, events: EventService | None = None) -> None:
        self._events = events or event_service
        self._participants: dict[str, ExecutionParticipant] = {}
        self._invocations: dict[str, ExecutionInvocation] = {}
        self._seed_defaults()

    def list_participants(self) -> list[ExecutionParticipant]:
        return [self._participants[pid] for pid in sorted(self._participants)]

    def get_participant(self, participant_id: str) -> ExecutionParticipant:
        try:
            return self._participants[participant_id]
        except KeyError as exc:
            raise ValueError(f"Participant is not registered: {participant_id}") from exc

    def register(
        self,
        participant: ExecutionParticipant,
        emit_event: bool = True,
    ) -> ExecutionParticipant:
        if participant.participant_id in self._participants:
            raise ValueError(f"Participant already registered: {participant.participant_id}")
        self._participants[participant.participant_id] = participant
        if emit_event:
            self._events.emit_event_sync(
                EventType.PARTICIPANT_REGISTERED,
                f"Participant registered: {participant.display_name}",
                metadata={"participant_id": participant.participant_id, "kind": participant.kind.value},
            )
        return participant

    def diagnostics(self) -> ExecutionParticipantRegistryDiagnostics:
        kinds: dict[str, int] = {}
        capabilities: dict[str, int] = {}
        for participant in self._participants.values():
            kinds[participant.kind.value] = kinds.get(participant.kind.value, 0) + 1
            for capability in participant.capability_manifest:
                capabilities[capability.capability_id] = capabilities.get(capability.capability_id, 0) + 1
        warnings = []
        if not self._participants:
            warnings.append("No execution participants are registered.")
        return ExecutionParticipantRegistryDiagnostics(
            status="healthy" if self._participants else "degraded",
            total_participants=len(self._participants),
            kinds=kinds,
            capabilities=dict(sorted(capabilities.items())),
            routing_policy="deterministic-human-governed",
            registry_views=["participant", "capability", "invocation"],
            warnings=warnings,
            metadata={"invocation_count": len(self._invocations)},
        )

    def route_capability(self, request: ExecutionCapabilityRouteRequest) -> ExecutionParticipantRegistry:
        eligible = self._eligible_participants(request)
        selected = eligible[0] if eligible else None
        if selected is not None:
            self._events.emit_event_sync(
                EventType.PARTICIPANT_SELECTED,
                f"Participant selected: {selected.display_name}",
                metadata={"participant_id": selected.participant_id, "capability_id": request.capability_id},
            )
        return ExecutionParticipantRegistry(
            participants=eligible,
            selected_participant_id=selected.participant_id if selected else None,
            eligible_participant_ids=[participant.participant_id for participant in eligible],
        )

    def list_capability_manifests(self) -> list[ExecutionCapabilityManifest]:
        manifests: list[ExecutionCapabilityManifest] = []
        for participant in self.list_participants():
            manifests.extend(participant.capability_manifest)
        return sorted(manifests, key=lambda manifest: (manifest.route_order, manifest.participant_id, manifest.capability_id))

    def create_invocation(
        self,
        capability_id: str,
        requested_by: str = "operator",
        input_payload: dict[str, Any] | None = None,
    ) -> ExecutionInvocation:
        route = self.route_capability(ExecutionCapabilityRouteRequest(capability_id=capability_id))
        if not route.selected_participant_id:
            raise ValueError(f"No participant can satisfy capability: {capability_id}")
        participant = self.get_participant(route.selected_participant_id)
        now = datetime.now(UTC).isoformat()
        invocation = ExecutionInvocation(
            invocation_id=f"inv-{uuid4().hex[:12]}",
            participant_id=participant.participant_id,
            capability_id=capability_id,
            requested_by=requested_by,
            input_payload=input_payload or {},
            created_at=now,
            updated_at=now,
        )
        self._invocations[invocation.invocation_id] = invocation
        self._transition(invocation.invocation_id, ExecutionInvocationState.VALIDATED)
        self._transition(invocation.invocation_id, ExecutionInvocationState.QUEUED)
        return self._invocations[invocation.invocation_id]

    def get_invocation(self, invocation_id: str) -> ExecutionInvocation:
        try:
            return self._invocations[invocation_id]
        except KeyError as exc:
            raise ValueError(f"Invocation is not registered: {invocation_id}") from exc

    def list_invocations(self) -> list[ExecutionInvocation]:
        return [self._invocations[iid] for iid in sorted(self._invocations)]

    def start_invocation(self, invocation_id: str) -> ExecutionInvocation:
        return self._transition(invocation_id, ExecutionInvocationState.EXECUTING)

    def mark_waiting(self, invocation_id: str, reason: str = "waiting") -> ExecutionInvocation:
        return self._transition(invocation_id, ExecutionInvocationState.WAITING, reason=reason)

    def mark_waiting_for_approval(self, invocation_id: str, reason: str = "approval required") -> ExecutionInvocation:
        return self._transition(invocation_id, ExecutionInvocationState.WAITING_FOR_APPROVAL, reason=reason)

    def complete_invocation(self, invocation_id: str, output_payload: dict[str, Any] | None = None) -> ExecutionInvocation:
        invocation = self.get_invocation(invocation_id)
        invocation.output_payload = output_payload or {}
        return self._transition(invocation_id, ExecutionInvocationState.COMPLETED)

    def fail_invocation(self, invocation_id: str, error: str) -> ExecutionInvocation:
        invocation = self.get_invocation(invocation_id)
        invocation.error = error
        return self._transition(invocation_id, ExecutionInvocationState.FAILED, reason=error)

    def cancel_invocation(self, invocation_id: str, reason: str = "cancelled") -> ExecutionInvocation:
        return self._transition(invocation_id, ExecutionInvocationState.CANCELLED, reason=reason)

    def interrupt_invocation(self, invocation_id: str, reason: str = "interrupted") -> ExecutionInvocation:
        return self._transition(invocation_id, ExecutionInvocationState.INTERRUPTED, reason=reason)

    def timed_out_invocation(self, invocation_id: str, reason: str = "timed out") -> ExecutionInvocation:
        return self._transition(invocation_id, ExecutionInvocationState.TIMED_OUT, reason=reason)

    def _transition(self, invocation_id: str, state: ExecutionInvocationState, reason: str | None = None) -> ExecutionInvocation:
        invocation = self.get_invocation(invocation_id)
        invocation.state = state
        invocation.updated_at = datetime.now(UTC).isoformat()
        if state == ExecutionInvocationState.EXECUTING and invocation.started_at is None:
            invocation.started_at = invocation.updated_at
        if state in {
            ExecutionInvocationState.COMPLETED,
            ExecutionInvocationState.FAILED,
            ExecutionInvocationState.CANCELLED,
            ExecutionInvocationState.TIMED_OUT,
            ExecutionInvocationState.INTERRUPTED,
        }:
            invocation.completed_at = invocation.updated_at
        event_type = self._event_type_for_state(state)
        invocation.events.append(event_type.value)
        self._events.emit_event_sync(
            event_type,
            reason or self._message_for_state(state),
            Severity.INFO,
            metadata={
                "invocation_id": invocation.invocation_id,
                "participant_id": invocation.participant_id,
                "capability_id": invocation.capability_id,
                "state": invocation.state.value,
                "input_payload": invocation.input_payload,
                "output_payload": invocation.output_payload,
                "metadata": invocation.metadata,
                "reason": reason,
            },
        )
        self._invocations[invocation_id] = invocation
        return invocation

    def _supports_capability(self, participant: ExecutionParticipant, capability_id: str) -> bool:
        return any(capability.capability_id == capability_id for capability in participant.capability_manifest)

    def _eligible_participants(self, request: ExecutionCapabilityRouteRequest) -> list[ExecutionParticipant]:
        eligible = [
            participant
            for participant in self.list_participants()
            if self._supports_capability(participant, request.capability_id)
            and (request.allow_unavailable or participant.lifecycle == ExecutionParticipantLifecycle.AVAILABLE)
            and (not request.preferred_kinds or participant.kind in request.preferred_kinds)
        ]
        return sorted(
            eligible,
            key=lambda participant: (
                participant.kind.value != "human",
                participant.kind.value,
                participant.participant_id,
            ),
        )

    def _event_type_for_state(self, state: ExecutionInvocationState) -> EventType:
        return {
            ExecutionInvocationState.VALIDATED: EventType.INVOCATION_VALIDATED,
            ExecutionInvocationState.QUEUED: EventType.INVOCATION_QUEUED,
            ExecutionInvocationState.EXECUTING: EventType.INVOCATION_STARTED,
            ExecutionInvocationState.WAITING: EventType.INVOCATION_WAITING,
            ExecutionInvocationState.WAITING_FOR_APPROVAL: EventType.INVOCATION_WAITING_FOR_APPROVAL,
            ExecutionInvocationState.COMPLETED: EventType.INVOCATION_COMPLETED,
            ExecutionInvocationState.FAILED: EventType.INVOCATION_FAILED,
            ExecutionInvocationState.CANCELLED: EventType.INVOCATION_CANCELLED,
            ExecutionInvocationState.TIMED_OUT: EventType.INVOCATION_TIMED_OUT,
            ExecutionInvocationState.INTERRUPTED: EventType.INVOCATION_INTERRUPTED,
            ExecutionInvocationState.CREATED: EventType.INVOCATION_CREATED,
        }[state]

    def _message_for_state(self, state: ExecutionInvocationState) -> str:
        return {
            ExecutionInvocationState.VALIDATED: "Invocation validated",
            ExecutionInvocationState.QUEUED: "Invocation queued",
            ExecutionInvocationState.EXECUTING: "Invocation started",
            ExecutionInvocationState.WAITING: "Invocation waiting",
            ExecutionInvocationState.WAITING_FOR_APPROVAL: "Invocation waiting for approval",
            ExecutionInvocationState.COMPLETED: "Invocation completed",
            ExecutionInvocationState.FAILED: "Invocation failed",
            ExecutionInvocationState.CANCELLED: "Invocation cancelled",
            ExecutionInvocationState.TIMED_OUT: "Invocation timed out",
            ExecutionInvocationState.INTERRUPTED: "Invocation interrupted",
            ExecutionInvocationState.CREATED: "Invocation created",
        }[state]

    def _seed_defaults(self) -> None:
        self.register(
            ExecutionParticipant(
                participant_id="human-operator",
                display_name="Human Operator",
                kind=ExecutionParticipantKind.HUMAN,
                identity={"role": "operator"},
                capabilities=[
                    ExecutionParticipantCapability(
                        capability_id="approval",
                        description="Approve, reject, interrupt, and inspect governed execution.",
                        operations=["approve", "reject", "interrupt", "inspect"],
                    )
                ],
                capability_manifest=[
                    ExecutionCapabilityManifest(
                        capability_id="approval",
                        participant_id="human-operator",
                        display_name="Human approval",
                        kind=ExecutionParticipantKind.HUMAN,
                        route_order=0,
                        description="Approve, reject, interrupt, and inspect governed execution.",
                        operations=["approve", "reject", "interrupt", "inspect"],
                        inputs=["decision"],
                        outputs=["approval"],
                        approval_required=True,
                        risk_level=ExecutionRiskLevel.LOW,
                        interrupt_support=True,
                        metadata={"source": "builtin"},
                    )
                ],
                lifecycle=ExecutionParticipantLifecycle.AVAILABLE,
                health=ExecutionParticipantHealth.HEALTHY,
                availability="authoritative",
                version="1.0.0",
                supported_operations=["approve", "interrupt", "inspect"],
                contract=ExecutionParticipantContract(
                    inputs=["decision"],
                    outputs=["approval"],
                    approval_required=True,
                    risk_level=ExecutionRiskLevel.LOW,
                    timeout_seconds=3600,
                    interrupt_support=True,
                ),
                metadata={"source": "builtin"},
            ),
            emit_event=False,
        )
        for tool in tool_registry_service.list_tools():
            self.register(
                ExecutionParticipant(
                    participant_id=f"tool:{tool.name}",
                    display_name=tool.name,
                    kind=ExecutionParticipantKind.LOCAL_TOOL,
                    identity={"tool_id": tool.id},
                    capabilities=[
                        ExecutionParticipantCapability(
                            capability_id=parameter.name,
                            description=parameter.name,
                            operations=["invoke"],
                        )
                        for parameter in tool_registry_service.list_parameters(tool.id)
                    ] or [ExecutionParticipantCapability(capability_id=tool.name, operations=["invoke"])],
                    capability_manifest=[
                        ExecutionCapabilityManifest(
                            capability_id=tool.name,
                            participant_id=f"tool:{tool.name}",
                            display_name=tool.name,
                            kind=ExecutionParticipantKind.LOCAL_TOOL,
                            route_order=1,
                            description=tool.description,
                            operations=["invoke", "inspect"],
                            inputs=["json"],
                            outputs=["json"],
                            artifacts=["file"],
                            approval_required=False,
                            risk_level=ExecutionRiskLevel.MEDIUM,
                            streaming_support=False,
                            interrupt_support=True,
                            lifecycle=ExecutionParticipantLifecycle.AVAILABLE if tool.enabled else ExecutionParticipantLifecycle.DISABLED,
                            health=ExecutionParticipantHealth.HEALTHY if tool.enabled else ExecutionParticipantHealth.DEGRADED,
                            availability="enabled" if tool.enabled else "disabled",
                            metadata={"tool_id": tool.id},
                        )
                    ],
                    lifecycle=ExecutionParticipantLifecycle.AVAILABLE if tool.enabled else ExecutionParticipantLifecycle.DISABLED,
                    health=ExecutionParticipantHealth.HEALTHY if tool.enabled else ExecutionParticipantHealth.DEGRADED,
                    availability="enabled" if tool.enabled else "disabled",
                    version=tool.updated_at.isoformat(),
                    supported_operations=["invoke", "inspect"],
                    contract=ExecutionParticipantContract(
                        inputs=["json"],
                        outputs=["json"],
                        artifacts=["file"],
                        approval_required=False,
                        risk_level=ExecutionRiskLevel.MEDIUM,
                        timeout_seconds=300,
                        streaming_support=False,
                        interrupt_support=True,
                    ),
                    metadata={"tool_id": tool.id},
                ),
                emit_event=False,
            )
        for manifest in agent_adapter_catalog_service.list_adapters().adapters:
            self.register(_participant_from_manifest(manifest), emit_event=False)
        for provider_id in provider_registry.providers():
            self.register(
                ExecutionParticipant(
                    participant_id=f"provider:{provider_id}",
                    display_name=provider_id,
                    kind=ExecutionParticipantKind.PROVIDER,
                    identity={"provider_id": provider_id},
                    capabilities=[
                        ExecutionParticipantCapability(capability_id=model, operations=["generate"])
                        for model in provider_registry.supported_models(provider_id)
                    ],
                    capability_manifest=[
                        ExecutionCapabilityManifest(
                            capability_id=model,
                            participant_id=f"provider:{provider_id}",
                            display_name=model,
                            kind=ExecutionParticipantKind.PROVIDER,
                            route_order=2,
                            operations=["generate", "stream"],
                            inputs=["prompt"],
                            outputs=["completion"],
                            artifacts=["response"],
                            approval_required=False,
                            risk_level=ExecutionRiskLevel.MEDIUM,
                            streaming_support=True,
                            interrupt_support=True,
                            metadata={"provider_id": provider_id},
                        )
                        for model in provider_registry.supported_models(provider_id)
                    ],
                    lifecycle=ExecutionParticipantLifecycle.AVAILABLE,
                    health=ExecutionParticipantHealth.HEALTHY,
                    availability="ready",
                    version="1.0.0",
                    supported_operations=["generate", "stream", "inspect"],
                    contract=ExecutionParticipantContract(
                        inputs=["prompt"],
                        outputs=["completion"],
                        artifacts=["response"],
                        approval_required=False,
                        risk_level=ExecutionRiskLevel.MEDIUM,
                        timeout_seconds=120,
                        streaming_support=True,
                        interrupt_support=True,
                    ),
                    metadata={"provider_id": provider_id},
                ),
                emit_event=False,
            )


def _participant_from_manifest(manifest: AgentCapabilityManifest) -> ExecutionParticipant:
    kind = {
        "hosted": ExecutionParticipantKind.PROVIDER,
        "local": ExecutionParticipantKind.LOCAL_TOOL,
        "mcp": ExecutionParticipantKind.MCP_SERVER,
        "a2a": ExecutionParticipantKind.A2A_AGENT,
    }.get(
        manifest.manifest.transport.value,
        ExecutionParticipantKind.EXTERNAL_AGENT,
    )
    return ExecutionParticipant(
        participant_id=f"agent:{manifest.manifest.adapter_id}",
        display_name=manifest.manifest.display_name,
        kind=kind,
        identity={
            "adapter_id": manifest.manifest.adapter_id,
            "transport": manifest.manifest.transport.value,
        },
        capabilities=[
            ExecutionParticipantCapability(capability_id=capability, operations=["execute"])
            for capability in manifest.manifest.supported_capabilities
        ],
        capability_manifest=[
            ExecutionCapabilityManifest(
                capability_id=capability,
                participant_id=f"agent:{manifest.manifest.adapter_id}",
                display_name=capability,
                kind=kind,
                route_order=3,
                description=manifest.manifest.description,
                operations=["execute", "inspect"],
                inputs=manifest.manifest.supported_capabilities,
                outputs=["result"],
                artifacts=["artifact"] if manifest.manifest.supports_artifacts else [],
                approval_required=manifest.manifest.supports_approvals,
                risk_level=ExecutionRiskLevel.MEDIUM,
                streaming_support=manifest.manifest.supports_streaming,
                interrupt_support=True,
                metadata=manifest.manifest.metadata,
            )
            for capability in manifest.manifest.supported_capabilities
        ],
        lifecycle=ExecutionParticipantLifecycle.AVAILABLE,
        health=ExecutionParticipantHealth.HEALTHY,
        availability="ready",
        version=manifest.manifest.version or "1.0.0",
        supported_operations=["execute", "stream", "inspect"],
        contract=ExecutionParticipantContract(
            inputs=manifest.manifest.supported_capabilities,
            outputs=["result"],
            artifacts=["artifact"] if manifest.manifest.supports_artifacts else [],
            approval_required=manifest.manifest.supports_approvals,
            risk_level=ExecutionRiskLevel.MEDIUM,
            timeout_seconds=600,
            streaming_support=manifest.manifest.supports_streaming,
            interrupt_support=True,
        ),
        metadata=manifest.manifest.metadata,
    )


execution_participant_registry_service = ExecutionParticipantRegistryService()
