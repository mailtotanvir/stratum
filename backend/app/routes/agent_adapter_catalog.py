from fastapi import APIRouter, HTTPException

from app.models.agent_adapter import AgentCapabilityManifest
from app.models.agent_adapter_catalog import (
    AgentAdapterCatalog,
    AgentAdapterRegistryDiagnostics,
    AgentEventNormalizationCatalog,
)
from app.services.agent_adapter_catalog_service import (
    agent_adapter_catalog_service,
)


router = APIRouter()


@router.get("/agent-adapters")
def list_agent_adapters() -> AgentAdapterCatalog:
    return agent_adapter_catalog_service.list_adapters()


@router.get("/agent-adapters/normalization")
def get_agent_event_normalization_catalog() -> AgentEventNormalizationCatalog:
    return agent_adapter_catalog_service.normalization_catalog()


@router.get("/agent-adapters/diagnostics")
def get_agent_adapter_registry_diagnostics() -> AgentAdapterRegistryDiagnostics:
    return agent_adapter_catalog_service.diagnostics()


@router.get("/agent-adapters/{adapter_id}")
def get_agent_adapter_manifest(adapter_id: str) -> AgentCapabilityManifest:
    try:
        return agent_adapter_catalog_service.get_manifest(adapter_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
