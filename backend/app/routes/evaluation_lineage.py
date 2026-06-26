from fastapi import APIRouter, HTTPException

from app.models.evaluation_lineage import (
    EvaluationEvidenceRecord,
    EvaluationEvidenceRecordCreate,
    EvaluationLineageProjection,
    EvaluationLineageRecord,
    EvaluationLineageRecordCreate,
)
from app.services.evaluation_lineage_projection_builder_service import (
    evaluation_lineage_projection_builder_service,
)
from app.services.evaluation_lineage_service import (
    EvaluationEvidenceAlreadyExistsError,
    EvaluationLineageAlreadyExistsError,
    EvaluationLineageNotFoundError,
    evaluation_lineage_service,
)


router = APIRouter()


@router.post("/evaluation-lineage")
def register_evaluation_lineage(
    request: EvaluationLineageRecordCreate,
) -> EvaluationLineageRecord:
    try:
        return evaluation_lineage_service.register_lineage(request)
    except EvaluationLineageAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/evaluation-lineage/evidence")
def register_evaluation_evidence(
    request: EvaluationEvidenceRecordCreate,
) -> EvaluationEvidenceRecord:
    try:
        return evaluation_lineage_service.register_evidence(request)
    except EvaluationEvidenceAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EvaluationLineageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluation-lineage")
def list_evaluation_lineage() -> list[EvaluationLineageRecord]:
    return evaluation_lineage_service.list_lineage()


@router.get("/evaluation-lineage/evidence")
def list_evaluation_evidence(
    lineage_id: str | None = None,
) -> list[EvaluationEvidenceRecord]:
    return evaluation_lineage_service.list_evidence(lineage_id=lineage_id)


@router.get("/evaluation-lineage/projection")
def get_evaluation_lineage_projection() -> EvaluationLineageProjection:
    return evaluation_lineage_projection_builder_service.build()
