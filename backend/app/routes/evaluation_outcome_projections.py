from fastapi import APIRouter, HTTPException

from app.models.evaluation_outcome_projection import EvaluationOutcomeRollup
from app.services.evaluation_outcome_projection_service import (
    EvaluationOutcomeRollupNotFoundError,
    evaluation_outcome_projection_service,
)


router = APIRouter()


@router.get("/runtime/evaluation-outcomes")
def list_evaluation_outcomes(
    target_type: str | None = None,
    session_id: str | None = None,
    decision_id: str | None = None,
    artifact_id: str | None = None,
    evaluation_type: str | None = None,
    status: str | None = None,
) -> list[EvaluationOutcomeRollup]:
    return evaluation_outcome_projection_service.list_outcome_rollups(
        target_type=target_type,
        session_id=session_id,
        decision_id=decision_id,
        artifact_id=artifact_id,
        evaluation_type=evaluation_type,
        status=status,
    )


@router.get("/runtime/evaluation-outcomes/{target_type}/{target_id}")
def get_evaluation_outcome(
    target_type: str,
    target_id: str,
) -> EvaluationOutcomeRollup:
    try:
        return evaluation_outcome_projection_service.get_outcome_rollup(
            target_type,
            target_id,
        )
    except EvaluationOutcomeRollupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
