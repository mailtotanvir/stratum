import pytest

from app.models.agent_adapter import AgentCapabilityManifest
from app.services.agent_adapter_registry_service import (
    AgentAdapterRegistryService,
)


class FakeAgentAdapter:
    def __init__(self, adapter_id: str = "agent-fake") -> None:
        self.adapter_id = adapter_id
        self.manifest = AgentCapabilityManifest(
            adapter_id=adapter_id,
            display_name="Fake Agent",
            supported_agent_types=["coding"],
            supported_capabilities=["tool_use"],
        )


def test_registry_lists_adapters_deterministically() -> None:
    registry = AgentAdapterRegistryService(
        [FakeAgentAdapter("agent-b"), FakeAgentAdapter("agent-a")]
    )

    assert [adapter.adapter_id for adapter in registry.list_adapters()] == [
        "agent-a",
        "agent-b",
    ]


def test_registry_returns_manifest_list() -> None:
    registry = AgentAdapterRegistryService([FakeAgentAdapter()])

    manifests = registry.list_manifests()

    assert [manifest.adapter_id for manifest in manifests] == ["agent-fake"]


def test_registry_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="Agent adapter already registered: agent-fake"):
        AgentAdapterRegistryService(
            [FakeAgentAdapter(), FakeAgentAdapter()]
        )


def test_unknown_adapter_raises_clear_error() -> None:
    registry = AgentAdapterRegistryService([FakeAgentAdapter()])

    with pytest.raises(ValueError, match="Agent adapter is not registered: missing"):
        registry.get_adapter("missing")
