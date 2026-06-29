from fastapi import APIRouter

from app.models.provider_health import ProviderHealth
from app.services.provider_health_service import (
    provider_health_service,
)

router = APIRouter()


@router.get("/providers/health")
def get_provider_health() -> ProviderHealth:
    return provider_health_service.health()
