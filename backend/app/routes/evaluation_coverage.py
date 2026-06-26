from fastapi import APIRouter, HTTPException

from app.models.evaluation_coverage import (
    CoverageMapping,
    CoverageMappingCreate,
    CoverageTarget,
    CoverageTargetCreate,
    EvaluationCoverageProjection,
)
from app.services.evaluation_coverage_projection_builder_service import (
    evaluation_coverage_projection_builder_service,
)
from app.services.evaluation_coverage_service import (
    CoverageMappingAlreadyExistsError,
    CoverageTargetAlreadyExistsError,
    CoverageTargetNotFoundError,
    evaluation_coverage_service,
)


router = APIRouter()


@router.post("/evaluation-coverage/targets")
def register_coverage_target(
    request: CoverageTargetCreate,
) -> CoverageTarget:
    try:
        return evaluation_coverage_service.register_target(request)
    except CoverageTargetAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/evaluation-coverage/mappings")
def register_coverage_mapping(
    request: CoverageMappingCreate,
) -> CoverageMapping:
    try:
        return evaluation_coverage_service.register_mapping(request)
    except CoverageMappingAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CoverageTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluation-coverage/targets")
def list_coverage_targets() -> list[CoverageTarget]:
    return evaluation_coverage_service.list_targets()


@router.get("/evaluation-coverage/mappings")
def list_coverage_mappings(
    target_id: str | None = None,
) -> list[CoverageMapping]:
    return evaluation_coverage_service.list_mappings(target_id=target_id)


@router.get("/evaluation-coverage/projection")
def get_evaluation_coverage_projection() -> EvaluationCoverageProjection:
    return evaluation_coverage_projection_builder_service.build()
