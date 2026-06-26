from fastapi import APIRouter

from app.services.evaluation_reconstruction_service import (
    EvaluationReconstructionResult,
    evaluation_reconstruction_service,
)


router = APIRouter()


@router.get("/evaluation-reconstruction")
def get_evaluation_reconstruction() -> EvaluationReconstructionResult:
    return evaluation_reconstruction_service.inspect()


@router.post("/evaluation-reconstruction/rebuild")
def rebuild_evaluation_reconstruction() -> EvaluationReconstructionResult:
    return evaluation_reconstruction_service.rebuild_all()
