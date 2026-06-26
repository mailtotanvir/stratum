from fastapi import APIRouter, HTTPException

from app.models.evaluation_registry import (
    EvaluationDefinition,
    EvaluationDefinitionCreate,
    EvaluationRegistryProjection,
    EvaluationSuite,
    EvaluationSuiteCreate,
)
from app.services.evaluation_registry_projection_builder_service import (
    evaluation_registry_projection_builder_service,
)
from app.services.evaluation_registry_service import (
    EvaluationDefinitionAlreadyExistsError,
    EvaluationDefinitionNotFoundError,
    EvaluationSuiteAlreadyExistsError,
    evaluation_registry_service,
)


router = APIRouter()


@router.post("/evaluation-registry/definitions")
def register_evaluation_definition(
    request: EvaluationDefinitionCreate,
) -> EvaluationDefinition:
    try:
        return evaluation_registry_service.register_definition(request)
    except EvaluationDefinitionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/evaluation-registry/suites")
def register_evaluation_suite(
    request: EvaluationSuiteCreate,
) -> EvaluationSuite:
    try:
        return evaluation_registry_service.register_suite(request)
    except EvaluationSuiteAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EvaluationDefinitionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluation-registry/definitions")
def list_evaluation_definitions() -> list[EvaluationDefinition]:
    return evaluation_registry_service.list_definitions()


@router.get("/evaluation-registry/suites")
def list_evaluation_suites() -> list[EvaluationSuite]:
    return evaluation_registry_service.list_suites()


@router.get("/evaluation-registry/projection")
def get_evaluation_registry_projection() -> EvaluationRegistryProjection:
    return evaluation_registry_projection_builder_service.build()
