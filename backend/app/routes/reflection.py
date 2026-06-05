import json

from fastapi import APIRouter, HTTPException

from app.db.schema import ReflectionRequestRecord
from app.models.reflection import ReflectionRequest
from app.services.reflection_service import (
    ReflectionRequestAlreadyResolvedError,
    ReflectionRequestNotFoundError,
    reflection_service,
)

router = APIRouter()


def to_reflection_request(record: ReflectionRequestRecord) -> ReflectionRequest:
    return ReflectionRequest(
        id=record.id,
        task_id=record.task_id,
        status=record.status,
        reasons=list(json.loads(record.reasons_json)),
        created_at=record.created_at.isoformat(),
        resolved_at=(
            record.resolved_at.isoformat()
            if record.resolved_at is not None
            else None
        ),
    )


@router.get("/reflections")
def list_reflections(
    status: str | None = None,
    task_id: str | None = None,
) -> list[ReflectionRequest]:
    return [
        to_reflection_request(record)
        for record in reflection_service.list_requests(
            status=status,
            task_id=task_id,
        )
    ]


@router.get("/reflections/{request_id}")
def get_reflection(request_id: str) -> ReflectionRequest:
    try:
        return to_reflection_request(reflection_service.get_request(request_id))
    except ReflectionRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reflections/{request_id}/resolve")
def resolve_reflection(request_id: str) -> ReflectionRequest:
    try:
        return to_reflection_request(reflection_service.resolve_request(request_id))
    except ReflectionRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReflectionRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
