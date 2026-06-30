from fastapi import APIRouter, HTTPException

from app.models.memory import RepositoryMemory, SessionMemory, WorkingMemory
from app.services.memory_reconstruction_service import memory_reconstruction_service

router = APIRouter()


@router.get("/runtime/memory/working")
def get_working_memory(session_id: str | None = None) -> WorkingMemory:
    return memory_reconstruction_service.reconstruct_working_memory(session_id)


@router.get("/runtime/memory/sessions/{session_id}")
def get_session_memory(session_id: str) -> SessionMemory:
    try:
        return memory_reconstruction_service.reconstruct_session_memory(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/memory/repository")
def get_repository_memory() -> RepositoryMemory:
    return memory_reconstruction_service.reconstruct_repository_memory()
