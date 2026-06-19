from fastapi import APIRouter, HTTPException

from app.models.evaluation_projection import (
    EvaluationProjection,
    EvaluationSummaryProjection,
)
from app.services.evaluation_record_projection_builder_service import (
    evaluation_record_projection_builder_service,
)
from app.services.evaluation_projection_service import (
    EvaluationSummaryProjectionNotFoundError,
    evaluation_projection_service,
)


router = APIRouter()


@router.get("/runtime/evaluation-projections")
def list_evaluation_projections(
    session_id: str | None = None,
    decision_id: str | None = None,
    artifact_id: str | None = None,
    evaluation_type: str | None = None,
    status: str | None = None,
) -> list[EvaluationSummaryProjection]:
    return evaluation_projection_service.list_evaluation_summaries(
        session_id=session_id,
        decision_id=decision_id,
        artifact_id=artifact_id,
        evaluation_type=evaluation_type,
        status=status,
    )


@router.get("/runtime/evaluation-projections/summary")
def get_evaluation_projection_summary(
    target_type: str | None = None,
    target_id: str | None = None,
    evaluation_type: str | None = None,
    outcome: str | None = None,
) -> EvaluationProjection:
    return evaluation_record_projection_builder_service.build(
        {
            "target_type": target_type,
            "target_id": target_id,
            "evaluation_type": evaluation_type,
            "outcome": outcome,
        }
    )


@router.get("/runtime/evaluation-projections/{evaluation_id}")
def get_evaluation_projection(
    evaluation_id: str,
) -> EvaluationSummaryProjection:
    try:
        return evaluation_projection_service.get_evaluation_summary(
            evaluation_id
        )
    except EvaluationSummaryProjectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
