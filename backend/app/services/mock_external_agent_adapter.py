from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.agent_adapter import (
    AgentAdapterTransport,
    AgentCapabilityManifest,
    AgentInvocationResult,
)


@dataclass
class _InvocationSnapshot:
    capability_id: str
    user_request: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MockExternalAgentAdapter:
    adapter_id = "agent-mock-external"

    def __init__(self) -> None:
        self.manifest = AgentCapabilityManifest(
            adapter_id=self.adapter_id,
            display_name="Mock External Agent",
            version="1.0.0",
            description=(
                "Built-in demo-only hosted agent adapter that simulates an "
                "external lifecycle without network or workspace writes."
            ),
            transport=AgentAdapterTransport.HOSTED,
            provider_family="mock",
            supported_agent_types=["coding", "research"],
            supported_capabilities=["plan", "observe", "approve", "artifact"],
            supported_modalities=["text"],
            supports_streaming=False,
            supports_tool_use=True,
            supports_approvals=True,
            supports_multi_agent=False,
            supports_memory=True,
            supports_artifacts=True,
            supports_observability=True,
            metadata={
                "built_in": True,
                "demo_only": True,
                "surface": "mock/demo",
                "external": True,
            },
        )
        self._invocations: dict[str, _InvocationSnapshot] = {}
        self.cancelled_invocations: list[str] = []

    def invoke(
        self,
        *,
        capability_id: str,
        invocation_id: str,
        user_request: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInvocationResult:
        payload = dict(metadata or {})
        snapshot = _InvocationSnapshot(
            capability_id=capability_id,
            user_request=user_request,
            metadata=payload,
        )
        self._invocations[invocation_id] = snapshot
        outcome = _outcome_from_metadata(payload)
        if outcome == "cancelled":
            status = "cancelled"
            summary = "Mock external agent invocation cancelled."
        elif outcome == "failed":
            status = "failed"
            summary = "Mock external agent invocation failed."
        else:
            status = "completed"
            summary = "Mock external agent invocation completed."
        return AgentInvocationResult(
            invocation_id=invocation_id,
            adapter_id=self.adapter_id,
            status=status,
            output=_output_for(capability_id, user_request, outcome),
            summary=summary,
            usage={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            artifacts=self.declare_artifacts(
                invocation_id=invocation_id,
                capability_id=capability_id,
                metadata=payload,
            ),
            metadata={
                "adapter_kind": "mock_external",
                "built_in": True,
                "demo_only": True,
                "invocation_id": invocation_id,
                "capability_id": capability_id,
                "outcome": status,
                "user_request": user_request,
            },
            error_type="mock_external_agent_failure" if status == "failed" else None,
            error_message="Deterministic mock failure requested."
            if status == "failed"
            else None,
        )

    def emit_events(
        self,
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload = dict(metadata or {})
        outcome = _outcome_from_metadata(payload)
        events = [
            {
                "source_event_type": "started",
                "message": "Mock external agent started",
                "metadata": {
                    "invocation_id": invocation_id,
                    "capability_id": capability_id,
                    "demo_only": True,
                },
            },
            {
                "source_event_type": "step_observed",
                "message": "Mock external agent observed a reasoning step",
                "metadata": {
                    "invocation_id": invocation_id,
                    "step": "reasoning",
                    "sequence": 1,
                },
            },
        ]
        if payload.get("approval_required", True):
            events.append(
                {
                    "source_event_type": "approval_requested",
                    "message": "Mock external agent requested approval",
                    "metadata": {
                        "invocation_id": invocation_id,
                        "approval_scope": capability_id,
                    },
                }
            )
        events.append(
            {
                "source_event_type": "artifact_declared",
                "message": "Mock external agent declared an artifact",
                "metadata": {
                    "invocation_id": invocation_id,
                    "artifact_path": f"artifacts/{invocation_id}/summary.md",
                    "writes_workspace_directly": False,
                },
            }
        )
        terminal_type = outcome if outcome in {"failed", "cancelled"} else "completed"
        events.append(
            {
                "source_event_type": terminal_type,
                "message": f"Mock external agent {terminal_type}",
                "metadata": {
                    "invocation_id": invocation_id,
                    "capability_id": capability_id,
                },
            }
        )
        return events

    def declare_artifacts(
        self,
        *,
        invocation_id: str,
        capability_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del capability_id
        payload = dict(metadata or {})
        return [
            {
                "path": f"artifacts/{invocation_id}/summary.md",
                "kind": "summary",
                "title": "Mock external agent summary",
                "description": "Demo artifact declaration only.",
                "metadata": payload,
                "writes_workspace_directly": False,
            }
        ]

    def cancel_invocation(self, invocation_id: str) -> bool:
        if invocation_id not in self._invocations:
            raise ValueError(f"Agent invocation is not registered: {invocation_id}")
        self.cancelled_invocations.append(invocation_id)
        return True


def _outcome_from_metadata(metadata: dict[str, Any]) -> str:
    outcome = str(metadata.get("outcome", "completed"))
    return outcome if outcome in {"completed", "failed", "cancelled"} else "completed"


def _output_for(capability_id: str, user_request: str, outcome: str) -> str:
    return (
        f"{capability_id}:{outcome}:{user_request}"
        if outcome != "completed"
        else f"{capability_id}:completed:{user_request}"
    )
