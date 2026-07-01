from __future__ import annotations

from datetime import UTC, datetime

from app.models.repository_intelligence import (
    DependencyOverviewEntry,
    ModuleMapEntry,
    RepositoryIntelligenceSummary,
    RuntimeInventoryEntry,
)
from app.services.agent_adapter_catalog_service import agent_adapter_catalog_service
from app.services.artifact_service import artifact_service
from app.services.event_service import event_service
from app.services.provider_configuration_service import provider_configuration_service
from app.services.runtime_workspace_service import runtime_workspace_service
from app.services.runtime_session_service import runtime_session_service
from app.services.skill_registry_service import skill_registry_service


class RepositoryIntelligenceService:
    def build(self) -> RepositoryIntelligenceSummary:
        workspace = runtime_workspace_service.configuration.workspace_id
        sessions = runtime_session_service.list_sessions()
        artifacts = artifact_service.list_artifacts()
        skills = skill_registry_service.list_registry().skills
        providers = provider_configuration_service.list_configurations()
        adapters = agent_adapter_catalog_service.list_adapters().adapters
        events = event_service.list_persisted_events()
        return RepositoryIntelligenceSummary(
            repository_id=workspace,
            generated_at=datetime.now(UTC),
            architecture_summary=(
                f"{len(sessions)} sessions, {len(artifacts)} artifacts, "
                f"{len(providers)} providers, {len(adapters)} adapters"
            ),
            module_map=[
                ModuleMapEntry(module_name="backend", path="backend/app", kind="service"),
                ModuleMapEntry(module_name="desktop", path="desktop/src", kind="console"),
            ],
            service_graph=[
                "event_service -> trace_service",
                "memory_reconstruction_service -> event_service/artifact_service/skill_registry_service",
                "runtime console -> runtime api",
            ],
            dependency_overview=[
                DependencyOverviewEntry(
                    name=provider.display_name,
                    version=provider.default_model,
                    scope="provider",
                )
                for provider in providers
            ],
            runtime_inventory=[
                RuntimeInventoryEntry(name=session.id, status=session.status, metadata={"task_id": session.task_id})
                for session in sessions
            ],
            provider_inventory=[
                RuntimeInventoryEntry(name=provider.provider_id, status="configured", metadata=provider.metadata)
                for provider in providers
            ],
            tool_inventory=[
                RuntimeInventoryEntry(name=adapter.manifest.adapter_id, status="registered", metadata=adapter.manifest.metadata)
                for adapter in adapters
            ],
            evidence_sources=[
                f"events:{len(events)}",
                f"artifacts:{len(artifacts)}",
                f"skills:{len(skills)}",
            ],
        )


repository_intelligence_service = RepositoryIntelligenceService()
