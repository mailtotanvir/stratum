from fastapi import APIRouter, HTTPException

from app.models.evaluation_accountability import (
    AccountabilityDecisionCreate,
    AccountabilityDecisionRecord,
    EvaluationAccountabilityProjection,
    EvaluationRun,
    EvaluationRunCreate,
    EvaluationScenario,
    EvaluationScenarioCreate,
)
from app.services.evaluation_accountability_service import (
    EvaluationRunNotFoundError,
    EvaluationScenarioAlreadyExistsError,
    EvaluationScenarioNotFoundError,
    evaluation_accountability_service,
)


router = APIRouter()


@router.post("/evaluation-accountability/scenarios")
def create_scenario(request: EvaluationScenarioCreate) -> EvaluationScenario:
    try:
        return evaluation_accountability_service.register_scenario(request)
    except EvaluationScenarioAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/evaluation-accountability/scenarios")
def list_scenarios() -> list[EvaluationScenario]:
    return evaluation_accountability_service.list_scenarios()


@router.post("/evaluation-accountability/runs")
def create_run(request: EvaluationRunCreate) -> EvaluationRun:
    try:
        return evaluation_accountability_service.record_run(request)
    except EvaluationScenarioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluation-accountability/runs")
def list_runs() -> list[EvaluationRun]:
    return evaluation_accountability_service.list_runs()


@router.get("/evaluation-accountability/scorecards")
def list_scorecards():
    return evaluation_accountability_service.build_projection().scorecards


@router.get("/evaluation-accountability/regressions")
def get_regressions():
    return evaluation_accountability_service.build_projection().regressions


@router.post("/evaluation-accountability/decisions")
def create_decision(
    request: AccountabilityDecisionCreate,
) -> AccountabilityDecisionRecord:
    return evaluation_accountability_service.record_decision(
        request.decision_id,
        request.target_type,
        request.target_id,
        request.decision_summary,
        request.runtime_event_id,
    )


@router.get("/evaluation-accountability/decisions")
def list_decisions() -> list[AccountabilityDecisionRecord]:
    return evaluation_accountability_service.list_decisions()


@router.get("/evaluation-accountability/projection")
def get_projection() -> EvaluationAccountabilityProjection:
    return evaluation_accountability_service.build_projection()
