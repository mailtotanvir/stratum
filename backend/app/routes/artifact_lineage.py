from fastapi import APIRouter, HTTPException

from app.models.artifact_lineage import (
    ArtifactLineageChain,
    ArtifactLineageEvents,
    ArtifactLineageRecord,
    ArtifactLineageSummary,
)
from app.services.artifact_lineage_service import (
    ArtifactLineageNotFoundError,
    artifact_lineage_service,
)


router = APIRouter()


@router.get("/runtime/artifact-lineage")
def artifact_lineage_records() -> list[ArtifactLineageRecord]:
    return artifact_lineage_service.list_records()


@router.get("/runtime/artifact-lineage/summary")
def artifact_lineage_summary() -> ArtifactLineageSummary:
    return artifact_lineage_service.summary()


@router.get("/runtime/artifact-lineage/{artifact_id}")
def artifact_lineage_chain(artifact_id: str) -> ArtifactLineageChain:
    try:
        return artifact_lineage_service.get_chain(artifact_id)
    except ArtifactLineageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/artifact-lineage/{artifact_id}/events")
def artifact_lineage_events(artifact_id: str) -> ArtifactLineageEvents:
    try:
        return artifact_lineage_service.related_events(artifact_id)
    except ArtifactLineageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
