from fastapi import APIRouter, HTTPException

from app.models.runtime_reconstruction import (
    RuntimeReconstructionSessionSummary,
    RuntimeReconstructionTimelineItem,
    RuntimeReconstructionView,
)
from app.services.runtime_reconstruction_service import (
    runtime_reconstruction_service,
)
from app.services.runtime_session_service import RuntimeSessionNotFoundError


router = APIRouter()


@router.get("/runtime/reconstruction/sessions")
def runtime_reconstruction_sessions() -> list[
    RuntimeReconstructionSessionSummary
]:
    return runtime_reconstruction_service.list_sessions()


@router.get("/runtime/reconstruction/sessions/{session_id}")
def runtime_reconstruction_session(
    session_id: str,
) -> RuntimeReconstructionView:
    try:
        return runtime_reconstruction_service.reconstruct(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/reconstruction/sessions/{session_id}/timeline")
def runtime_reconstruction_timeline(
    session_id: str,
) -> list[RuntimeReconstructionTimelineItem]:
    try:
        return runtime_reconstruction_service.timeline(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
