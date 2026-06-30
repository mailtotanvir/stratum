from dataclasses import dataclass

from app.models.agent_adapter import (
    AgentAdapterTransport,
    AgentCapabilityManifest,
)
from app.models.agent_adapter_catalog import (
    AgentAdapterCatalog,
    AgentAdapterCatalogEntry,
    AgentAdapterRegistryDiagnostics,
    AgentAdapterRegistryHealthStatus,
    AgentEventNormalizationCatalog,
)
from app.models.runtime_event import EventType, Severity
from app.services.agent_adapter_registry_service import (
    AgentAdapterProtocol,
    AgentAdapterRegistryService,
)
from app.services.mock_external_agent_adapter import MockExternalAgentAdapter


@dataclass(frozen=True)
class BuiltInAgentAdapterDefinition:
    manifest: AgentCapabilityManifest


BUILT_IN_AGENT_ADAPTER_DEFINITIONS = [
    BuiltInAgentAdapterDefinition(
        manifest=AgentCapabilityManifest(
            adapter_id="agent-fake",
            display_name="Fake Agent",
            version="1.0.0",
            description="Deterministic built-in agent adapter used for catalog reads.",
            transport=AgentAdapterTransport.LOCAL,
            supported_agent_types=["coding"],
            supported_capabilities=["tool_use", "memory"],
            supported_modalities=["text"],
            supports_tool_use=True,
            supports_memory=True,
        )
    ),
    BuiltInAgentAdapterDefinition(
        manifest=AgentCapabilityManifest(
            adapter_id="agent-example",
            display_name="Example Agent",
            version="1.0.0",
            description="Deterministic built-in example adapter used for catalog reads.",
            transport=AgentAdapterTransport.CUSTOM,
            supported_agent_types=["research"],
            supported_capabilities=["planning"],
            supported_modalities=["text"],
        )
    ),
    BuiltInAgentAdapterDefinition(
        manifest=MockExternalAgentAdapter().manifest,
    ),
]


class _StaticAgentAdapter:
    def __init__(self, manifest: AgentCapabilityManifest) -> None:
        self.adapter_id = manifest.adapter_id
        self.manifest = manifest


class AgentAdapterCatalogService:
    def __init__(
        self,
        registry: AgentAdapterRegistryService | None = None,
        built_ins: list[BuiltInAgentAdapterDefinition] | None = None,
    ) -> None:
        self._registry = (
            registry
            if registry is not None
            else self._build_registry(
                built_ins or BUILT_IN_AGENT_ADAPTER_DEFINITIONS
            )
        )

    def list_adapters(self) -> AgentAdapterCatalog:
        return AgentAdapterCatalog(
            adapters=[
                AgentAdapterCatalogEntry(manifest=adapter.manifest)
                for adapter in self._registry.list_adapters()
            ]
        )

    @property
    def registry(self) -> AgentAdapterRegistryService:
        return self._registry

    def get_manifest(self, adapter_id: str) -> AgentCapabilityManifest:
        return self._registry.get_adapter(adapter_id).manifest

    def diagnostics(self) -> AgentAdapterRegistryDiagnostics:
        manifests = self._registry.list_manifests()
        adapter_ids = [manifest.adapter_id for manifest in manifests]
        duplicate_adapter_ids = _duplicate_ids(adapter_ids)
        invalid_adapter_ids = [
            manifest.adapter_id
            for manifest in manifests
            if _is_invalid_manifest(manifest)
        ]
        warnings: list[str] = []
        status: AgentAdapterRegistryHealthStatus = "healthy"
        if duplicate_adapter_ids or invalid_adapter_ids:
            status = "degraded"
        if duplicate_adapter_ids:
            warnings.append("Duplicate agent adapter definitions were detected.")
        if invalid_adapter_ids:
            warnings.append("Invalid agent adapter definitions were detected.")
        return AgentAdapterRegistryDiagnostics(
            status=status,
            total_registered=len(manifests),
            duplicate_adapter_ids=duplicate_adapter_ids,
            invalid_adapter_ids=invalid_adapter_ids,
            warnings=warnings,
        )

    def normalization_catalog(self) -> AgentEventNormalizationCatalog:
        return AgentEventNormalizationCatalog(
            source_event_kinds=sorted(_event_type_map().keys()),
            runtime_event_types=sorted(
                {event_type.value for event_type in _event_type_map().values()}
            ),
            severities=sorted(severity.value for severity in Severity),
        )

    def _build_registry(
        self,
        built_ins: list[BuiltInAgentAdapterDefinition],
    ) -> AgentAdapterRegistryService:
        adapters: list[AgentAdapterProtocol] = [
            _StaticAgentAdapter(definition.manifest) for definition in built_ins
        ]
        return AgentAdapterRegistryService(adapters)


def _event_type_map() -> dict[str, EventType]:
    from app.services.agent_event_bridge_service import (
        agent_event_bridge_service,
    )

    return dict(agent_event_bridge_service._event_type_map)


def _duplicate_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return sorted(duplicates)


def _is_invalid_manifest(manifest: AgentCapabilityManifest) -> bool:
    return not manifest.supported_agent_types and not manifest.supported_capabilities


agent_adapter_catalog_service = AgentAdapterCatalogService()
