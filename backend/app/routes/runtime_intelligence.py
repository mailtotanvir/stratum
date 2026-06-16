from fastapi import APIRouter, HTTPException

from app.models.runtime_intelligence import (
    RuntimeActivitySummary,
    RuntimeIntegritySummary,
    RuntimeIntelligenceSummary,
    RuntimeRiskSummary,
)
from app.services.runtime_intelligence_service import (
    RuntimeIntelligenceGenerationError,
    runtime_intelligence_service,
)


router = APIRouter()


@router.get("/runtime/intelligence")
def get_runtime_intelligence() -> RuntimeIntelligenceSummary:
    try:
        return runtime_intelligence_service.generate()
    except RuntimeIntelligenceGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/intelligence/risks")
def get_runtime_intelligence_risks() -> RuntimeRiskSummary:
    try:
        return runtime_intelligence_service.risks()
    except RuntimeIntelligenceGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/intelligence/activity")
def get_runtime_intelligence_activity() -> RuntimeActivitySummary:
    try:
        return runtime_intelligence_service.activity()
    except RuntimeIntelligenceGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/intelligence/integrity")
def get_runtime_intelligence_integrity() -> RuntimeIntegritySummary:
    try:
        return runtime_intelligence_service.integrity()
    except RuntimeIntelligenceGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
