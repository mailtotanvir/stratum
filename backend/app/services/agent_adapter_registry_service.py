from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from app.models.agent_adapter import AgentCapabilityManifest


@runtime_checkable
class AgentAdapterProtocol(Protocol):
    adapter_id: str
    manifest: AgentCapabilityManifest


class AgentAdapterRegistryService:
    def __init__(self, adapters: Iterable[AgentAdapterProtocol] | None = None) -> None:
        self._adapters: dict[str, AgentAdapterProtocol] = {}
        for adapter in adapters or []:
            self._register(adapter)

    def list_adapters(self) -> list[AgentAdapterProtocol]:
        return [self._adapters[adapter_id] for adapter_id in sorted(self._adapters)]

    def list_manifests(self) -> list[AgentCapabilityManifest]:
        return [adapter.manifest for adapter in self.list_adapters()]

    def get_adapter(self, adapter_id: str) -> AgentAdapterProtocol:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise ValueError(f"Agent adapter is not registered: {adapter_id}") from exc

    def has_adapter(self, adapter_id: str) -> bool:
        return adapter_id in self._adapters

    def register(self, adapter: AgentAdapterProtocol) -> None:
        self._register(adapter)

    def _register(self, adapter: AgentAdapterProtocol) -> None:
        adapter_id = adapter.adapter_id
        if adapter_id in self._adapters:
            raise ValueError(f"Agent adapter already registered: {adapter_id}")
        self._adapters[adapter_id] = adapter


agent_adapter_registry_service = AgentAdapterRegistryService()
