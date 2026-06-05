import json

from fastapi import APIRouter, HTTPException

from app.db.schema import ArtifactRecord
from app.models.artifact import Artifact, ArtifactCreate
from app.services.artifact_service import (
    ArtifactNotFoundError,
    artifact_service,
)

router = APIRouter()


def to_artifact(record: ArtifactRecord) -> Artifact:
    return Artifact(
        id=record.id,
        task_id=record.task_id,
        proposal_id=record.proposal_id,
        path=record.path,
        kind=record.kind,
        created_at=record.created_at.isoformat(),
        metadata=(
            dict(json.loads(record.metadata_json))
            if record.metadata_json is not None
            else None
        ),
    )


@router.post("/artifacts")
def create_artifact(request: ArtifactCreate) -> Artifact:
    return to_artifact(
        artifact_service.create_artifact(
            path=request.path,
            kind=request.kind.value,
            task_id=request.task_id,
            proposal_id=request.proposal_id,
            metadata=request.metadata,
        )
    )


@router.get("/artifacts")
def list_artifacts(
    task_id: str | None = None,
    proposal_id: str | None = None,
    kind: str | None = None,
) -> list[Artifact]:
    return [
        to_artifact(record)
        for record in artifact_service.list_artifacts(
            task_id=task_id,
            proposal_id=proposal_id,
            kind=kind,
        )
    ]


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> Artifact:
    try:
        return to_artifact(artifact_service.get_artifact(artifact_id))
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
