from fastapi import APIRouter, HTTPException

from app.models.evaluation_drift import (
    EvaluationDriftBaseline,
    EvaluationDriftBaselineCreate,
    EvaluationDriftObservation,
    EvaluationDriftObservationCreate,
    EvaluationDriftProjection,
)
from app.services.evaluation_drift_projection_builder_service import (
    evaluation_drift_projection_builder_service,
)
from app.services.evaluation_drift_service import (
    EvaluationDriftBaselineAlreadyExistsError,
    EvaluationDriftObservationAlreadyExistsError,
    evaluation_drift_service,
)


router = APIRouter()


@router.post("/evaluation-drift/baselines")
def register_evaluation_drift_baseline(
    request: EvaluationDriftBaselineCreate,
) -> EvaluationDriftBaseline:
    try:
        return evaluation_drift_service.register_baseline(request)
    except EvaluationDriftBaselineAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/evaluation-drift/observations")
def register_evaluation_drift_observation(
    request: EvaluationDriftObservationCreate,
) -> EvaluationDriftObservation:
    try:
        return evaluation_drift_service.register_observation(request)
    except EvaluationDriftObservationAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/evaluation-drift/baselines")
def list_evaluation_drift_baselines() -> list[EvaluationDriftBaseline]:
    return evaluation_drift_service.list_baselines()


@router.get("/evaluation-drift/observations")
def list_evaluation_drift_observations() -> list[EvaluationDriftObservation]:
    return evaluation_drift_service.list_observations()


@router.get("/evaluation-drift/projection")
def get_evaluation_drift_projection() -> EvaluationDriftProjection:
    return evaluation_drift_projection_builder_service.build()
