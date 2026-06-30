from fastapi import APIRouter

from app.models.transformation_history import (
    ArtifactRecordView,
    PatchRecordView,
    RepositoryChangeSummary,
    TransformationHistoryProjection,
)
from app.services.transformation_history_service import (
    transformation_history_service,
)

router = APIRouter()


@router.get("/runtime/artifacts")
def list_artifact_records() -> list[ArtifactRecordView]:
    return transformation_history_service.artifacts()


@router.get("/runtime/patches")
def list_patch_records() -> list[PatchRecordView]:
    return transformation_history_service.patches()


@router.get("/runtime/repository-change-summary")
def get_repository_change_summary() -> RepositoryChangeSummary:
    return transformation_history_service.repository_change_summary()


@router.get("/runtime/transformation-history")
def get_transformation_history() -> TransformationHistoryProjection:
    return transformation_history_service.history()

