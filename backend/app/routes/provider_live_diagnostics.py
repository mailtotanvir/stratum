from fastapi import APIRouter

from app.models.provider_live_diagnostics import ProviderLiveDiagnostics
from app.services.provider_live_diagnostics_service import (
    provider_live_diagnostics_service,
)


router = APIRouter()


@router.get("/providers/live/diagnostics")
def get_provider_live_diagnostics() -> ProviderLiveDiagnostics:
    return provider_live_diagnostics_service.inspect_environment()
