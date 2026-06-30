from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from app.models.agent_adapter import (
    AgentCapabilityManifest,
    AgentEventBridgeEvent,
    AgentInvocationResult,
)
from app.models.runtime_event import EventType
from app.services.agent_event_bridge_service import AgentEventBridgeService


@runtime_checkable
class AgentAdapterContractProtocol(Protocol):
    adapter_id: str
    manifest: AgentCapabilityManifest

    def invoke(
        self,
        *,
        capability_id: str,
        invocation_id: str,
        user_request: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationResult: ...

    def emit_events(
        self,
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def declare_artifacts(
        self,
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def cancel_invocation(self, invocation_id: str) -> bool: ...


@dataclass(frozen=True)
class AgentAdapterContractResult:
    manifest: AgentCapabilityManifest
    invocation_result: AgentInvocationResult
    normalized_events: list[AgentEventBridgeEvent] = field(default_factory=list)
    declared_artifacts: list[dict[str, Any]] = field(default_factory=list)
    cancellation_supported: bool = False


class AgentAdapterContractHarness:
    def __init__(self, bridge: AgentEventBridgeService | None = None) -> None:
        self._bridge = bridge or AgentEventBridgeService()

    def validate(
        self,
        adapter: AgentAdapterContractProtocol,
        *,
        capability_id: str,
        invocation_id: str = "invocation-1",
        user_request: str = "Run contract harness",
        metadata: dict[str, Any] | None = None,
    ) -> AgentAdapterContractResult:
        self._validate_manifest(adapter.manifest)
        self._validate_capability(adapter.manifest, capability_id)

        invocation_result = adapter.invoke(
            capability_id=capability_id,
            invocation_id=invocation_id,
            user_request=user_request,
            metadata=metadata or {},
        )
        self._validate_invocation_result(invocation_result, adapter.adapter_id)

        raw_events = adapter.emit_events(
            invocation_id=invocation_id,
            capability_id=capability_id,
            metadata=metadata or {},
        )
        normalized_events = [
            self._bridge.normalize(
                source_event_type=event["source_event_type"],
                message=event["message"],
                metadata=event.get("metadata"),
                severity=event.get("severity", "info"),
            )
            for event in raw_events
        ]
        self._validate_normalized_events(normalized_events)

        declared_artifacts = adapter.declare_artifacts(
            invocation_id=invocation_id,
            capability_id=capability_id,
            metadata=metadata or {},
        )
        self._validate_artifacts(declared_artifacts)

        cancellation_supported = self._validate_cancellation(adapter, invocation_id)

        return AgentAdapterContractResult(
            manifest=adapter.manifest,
            invocation_result=invocation_result,
            normalized_events=normalized_events,
            declared_artifacts=declared_artifacts,
            cancellation_supported=cancellation_supported,
        )

    def _validate_manifest(self, manifest: AgentCapabilityManifest) -> None:
        try:
            manifest.__class__.model_validate(manifest.model_dump())
        except ValidationError as exc:
            raise ValueError("Invalid capability manifest") from exc
        if not manifest.adapter_id.strip():
            raise ValueError("Capability manifest must declare adapter_id")
        if not manifest.display_name.strip():
            raise ValueError("Capability manifest must declare display_name")

    def _validate_capability(
        self, manifest: AgentCapabilityManifest, capability_id: str
    ) -> None:
        if capability_id not in manifest.supported_capabilities:
            raise ValueError(f"Capability is not supported: {capability_id}")

    def _validate_invocation_result(
        self, result: AgentInvocationResult, adapter_id: str
    ) -> None:
        if result.adapter_id != adapter_id:
            raise ValueError("Invocation result adapter_id mismatch")
        if not result.invocation_id.strip():
            raise ValueError("Invocation result must declare invocation_id")
        if result.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Invocation result must be terminal and deterministic")
        if "invocation_id" not in result.metadata:
            raise ValueError("Invocation result must include deterministic metadata")
        if result.metadata["invocation_id"] != result.invocation_id:
            raise ValueError("Invocation result metadata must echo invocation_id")

    def _validate_normalized_events(
        self, events: list[AgentEventBridgeEvent]
    ) -> None:
        if not events:
            raise ValueError("Adapter must emit at least one normalized event")
        for event in events:
            if event.runtime_event_type not in {
                event_type.value for event_type in EventType
            }:
                raise ValueError("Adapter emitted an invalid runtime event type")

    def _validate_artifacts(self, artifacts: list[dict[str, Any]]) -> None:
        for artifact in artifacts:
            if "path" not in artifact or not artifact["path"]:
                raise ValueError("Artifact declarations must include a path")
            if artifact.get("writes_workspace_directly") is True:
                raise ValueError(
                    "Adapters must not write directly to workspace artifacts"
                )

    def _validate_cancellation(
        self,
        adapter: AgentAdapterContractProtocol,
        invocation_id: str,
    ) -> bool:
        try:
            return bool(adapter.cancel_invocation(invocation_id))
        except NotImplementedError:
            return False
