from fastapi import APIRouter

from app.models.evaluation_diagnostics import EvaluationDiagnostics
from app.services.evaluation_diagnostics_service import (
    evaluation_diagnostics_service,
)


router = APIRouter()


@router.get("/runtime/evaluation-diagnostics")
@router.get("/evaluation-diagnostics")
def get_evaluation_diagnostics() -> EvaluationDiagnostics:
    return evaluation_diagnostics_service.generate()


@router.get("/evaluation-diagnostics/projection")
def get_evaluation_diagnostics_projection():
    return evaluation_diagnostics_service.projection()
