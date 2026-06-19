from fastapi import APIRouter, HTTPException

from app.models.evaluation_record import (
    EvaluationOutcome,
    EvaluationRecord,
    EvaluationRecordCreate,
    EvaluationTargetType,
)
from app.services.evaluation_record_service import (
    EvaluationRecordNotFoundError,
    evaluation_record_service,
)


router = APIRouter()


@router.post("/runtime/evaluations")
def create_runtime_evaluation(
    request: EvaluationRecordCreate,
) -> EvaluationRecord:
    return evaluation_record_service.create_record(request)


@router.get("/runtime/evaluations")
def list_runtime_evaluations(
    target_type: EvaluationTargetType | None = None,
    target_id: str | None = None,
    evaluation_type: str | None = None,
    outcome: EvaluationOutcome | None = None,
) -> list[EvaluationRecord]:
    return evaluation_record_service.list_records(
        target_type=target_type,
        target_id=target_id,
        evaluation_type=evaluation_type,
        outcome=outcome,
    )


@router.get("/runtime/evaluations/{evaluation_id}")
def get_runtime_evaluation(evaluation_id: str) -> EvaluationRecord:
    try:
        return evaluation_record_service.get_record(evaluation_id)
    except EvaluationRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
