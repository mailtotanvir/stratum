from fastapi import APIRouter, HTTPException

from app.models.runtime_dashboard import RuntimeDashboard
from app.models.runtime_health import RuntimeHealthStatus
from app.services.runtime_dashboard_service import (
    RuntimeDashboardGenerationError,
    runtime_dashboard_service,
)
from app.services.runtime_health_service import runtime_health_service


router = APIRouter()


@router.get("/observability/dashboard")
def get_runtime_observability_dashboard() -> RuntimeDashboard:
    try:
        return runtime_dashboard_service.generate()
    except RuntimeDashboardGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/observability/health")
def get_runtime_health() -> RuntimeHealthStatus:
    return runtime_health_service.evaluate()
