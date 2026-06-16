from fastapi import APIRouter, HTTPException

from app.models.provider_observability import (
    ModelUsageSummary,
    ProviderCostSummary,
    ProviderObservabilityReport,
)
from app.services.provider_observability_service import (
    ProviderObservabilityGenerationError,
    provider_observability_service,
)


router = APIRouter()


@router.get("/runtime/providers/observability")
def get_provider_observability() -> ProviderObservabilityReport:
    try:
        return provider_observability_service.generate()
    except ProviderObservabilityGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/providers/observability/{provider_name}")
def get_provider_observability_detail(
    provider_name: str,
) -> ProviderObservabilityReport:
    try:
        return provider_observability_service.generate(
            provider_name=provider_name,
        )
    except ProviderObservabilityGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/providers/models")
def get_provider_model_usage() -> list[ModelUsageSummary]:
    try:
        return provider_observability_service.model_usage()
    except ProviderObservabilityGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/providers/costs")
def get_provider_costs() -> list[ProviderCostSummary]:
    try:
        return provider_observability_service.cost_summary()
    except ProviderObservabilityGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
