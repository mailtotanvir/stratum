from fastapi import APIRouter, HTTPException

from app.models.transformation_session import (
    TransformationSessionCollection,
    TransformationSessionCreateRequest,
    TransformationSessionSummary,
)
from app.services.transformation_session_service import transformation_session_service

router = APIRouter()


@router.get("/runtime/transformation-sessions")
def list_transformation_sessions() -> TransformationSessionCollection:
    items = transformation_session_service.list_sessions()
    return TransformationSessionCollection(items=items, total=len(items))


@router.post("/runtime/transformation-sessions")
def create_transformation_session(
    request: TransformationSessionCreateRequest,
) -> TransformationSessionSummary:
    return transformation_session_service.create(request)


@router.get("/runtime/transformation-sessions/{transformation_id}")
def get_transformation_session(
    transformation_id: str,
) -> TransformationSessionSummary:
    try:
        return transformation_session_service.get_session(transformation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

