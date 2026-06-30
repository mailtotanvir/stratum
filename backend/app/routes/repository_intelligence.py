from fastapi import APIRouter

from app.models.repository_intelligence import RepositoryIntelligenceSummary
from app.services.repository_intelligence_service import (
    repository_intelligence_service,
)

router = APIRouter()


@router.get("/runtime/repository-intelligence")
def get_repository_intelligence() -> RepositoryIntelligenceSummary:
    return repository_intelligence_service.build()

