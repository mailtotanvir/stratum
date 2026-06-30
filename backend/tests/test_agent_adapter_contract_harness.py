from __future__ import annotations

from typing import Any

import pytest

from app.models.agent_adapter import (
    AgentAdapterTransport,
    AgentCapabilityManifest,
    AgentInvocationResult,
)
from app.services.agent_adapter_contract_harness import (
    AgentAdapterContractHarness,
)


class FakeContractAdapter:
    def __init__(self) -> None:
        self.adapter_id = "agent-contract-fake"
        self.manifest = AgentCapabilityManifest(
            adapter_id=self.adapter_id,
            display_name="Contract Fake Agent",
            version="1.0.0",
            transport=AgentAdapterTransport.LOCAL,
            supported_agent_types=["coding"],
            supported_capabilities=["plan", "observe"],
            supported_modalities=["text"],
            supports_artifacts=True,
            supports_observability=True,
        )
        self.cancelled: list[str] = []

    def invoke(
        self,
        *,
        capability_id: str,
        invocation_id: str,
        user_request: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationResult:
        del user_request
        payload = dict(metadata or {})
        payload.update(
            {
                "adapter_id": self.adapter_id,
                "capability_id": capability_id,
                "invocation_id": invocation_id,
                "deterministic": True,
            }
        )
        return AgentInvocationResult(
            invocation_id=invocation_id,
            adapter_id=self.adapter_id,
            status="completed",
            output=f"{capability_id}:{invocation_id}",
            summary="Deterministic fake adapter result",
            usage={"input_tokens": 1, "output_tokens": 1},
            metadata=payload,
        )

    def emit_events(
        self,
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "source_event_type": "started",
                "message": "Invocation started",
                "metadata": {
                    "invocation_id": invocation_id,
                    "capability_id": capability_id,
                    **dict(metadata or {}),
                },
            },
            {
                "source_event_type": "completed",
                "message": "Invocation completed",
                "metadata": {
                    "invocation_id": invocation_id,
                    "capability_id": capability_id,
                    **dict(metadata or {}),
                },
            },
        ]

    def declare_artifacts(
        self,
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del capability_id
        return [
            {
                "path": f"artifacts/{invocation_id}/result.md",
                "kind": "report",
                "metadata": dict(metadata or {}),
                "writes_workspace_directly": False,
            }
        ]

    def cancel_invocation(self, invocation_id: str) -> bool:
        self.cancelled.append(invocation_id)
        return True


class UnsupportedCancellationAdapter(FakeContractAdapter):
    def cancel_invocation(self, invocation_id: str) -> bool:
        del invocation_id
        raise NotImplementedError


def test_contract_harness_accepts_valid_adapter() -> None:
    harness = AgentAdapterContractHarness()
    adapter = FakeContractAdapter()

    result = harness.validate(adapter, capability_id="plan")
    repeat = harness.validate(adapter, capability_id="plan")

    assert result.manifest.adapter_id == "agent-contract-fake"
    assert result.invocation_result.metadata["deterministic"] is True
    assert result.invocation_result.metadata == repeat.invocation_result.metadata
    assert [event.runtime_event_type for event in result.normalized_events] == [
        "agent_execution_started",
        "agent_execution_completed",
    ]
    assert result.declared_artifacts[0]["path"] == "artifacts/invocation-1/result.md"
    assert result.cancellation_supported is True
    assert adapter.cancelled == ["invocation-1", "invocation-1"]


def test_contract_harness_rejects_undeclared_capability() -> None:
    harness = AgentAdapterContractHarness()

    with pytest.raises(ValueError, match="Capability is not supported: write"):
        harness.validate(FakeContractAdapter(), capability_id="write")


def test_contract_harness_allows_unsupported_cancellation_declared_via_error() -> None:
    harness = AgentAdapterContractHarness()

    result = harness.validate(UnsupportedCancellationAdapter(), capability_id="plan")

    assert result.cancellation_supported is False


def test_contract_harness_rejects_workspace_direct_write_declarations() -> None:
    adapter = FakeContractAdapter()

    def declare_artifacts(
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del capability_id, metadata
        return [
            {
                "path": f"artifacts/{invocation_id}/result.md",
                "writes_workspace_directly": True,
            }
        ]

    adapter.declare_artifacts = declare_artifacts  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="must not write directly to workspace"):
        AgentAdapterContractHarness().validate(adapter, capability_id="plan")
