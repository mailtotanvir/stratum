from fastapi import APIRouter

from app.models.repository_intelligence import RepositoryIntelligenceSummary
from app.services.repository_intelligence_service import (
    repository_intelligence_service,
)

router = APIRouter()


@router.get("/runtime/repository-intelligence")
def get_repository_intelligence() -> RepositoryIntelligenceSummary:
    return repository_intelligence_service.build()


@router.get("/runtime/repository-intelligence/diagnostics")
def get_repository_intelligence_diagnostics() -> dict[str, object]:
    summary = repository_intelligence_service.build()
    return {
        "repository_id": summary.repository_id,
        "generated_at": summary.generated_at,
        "module_count": len(summary.module_map),
        "runtime_inventory_count": len(summary.runtime_inventory),
        "provider_inventory_count": len(summary.provider_inventory),
        "tool_inventory_count": len(summary.tool_inventory),
        "evidence_sources": summary.evidence_sources,
    }
