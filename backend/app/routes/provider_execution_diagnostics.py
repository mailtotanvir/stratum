from fastapi import APIRouter

from app.models.provider_execution_diagnostics import (
    ProviderExecutionDiagnostics,
)
from app.services.provider_execution_diagnostics_service import (
    provider_execution_diagnostics_service,
)


router = APIRouter()


@router.get("/runtime/provider-execution/diagnostics")
def get_provider_execution_diagnostics() -> ProviderExecutionDiagnostics:
    return provider_execution_diagnostics_service.get_diagnostics()
