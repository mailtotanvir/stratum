from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.proposal_service import ProposalNotFoundError
from app.services.reconstruction_service import reconstruction_service
from app.services.task_service import TaskNotFoundError

router = APIRouter()


@router.get("/reconstruct/tasks")
def reconstruct_tasks() -> list[dict[str, Any]]:
    return reconstruction_service.reconstruct_all_task_states()


@router.get("/reconstruct/tasks/consistency")
def task_consistency() -> dict[str, Any]:
    return reconstruction_service.task_consistency_health()


@router.get("/reconstruct/tasks/{task_id}")
def reconstruct_task(task_id: str) -> dict[str, Any]:
    return reconstruction_service.reconstruct_task_state(task_id)


@router.get("/reconstruct/tasks/{task_id}/compare")
def compare_task(task_id: str) -> dict[str, Any]:
    try:
        return reconstruction_service.compare_task_record_to_events(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reconstruct/proposals")
def reconstruct_proposals() -> list[dict[str, Any]]:
    return reconstruction_service.reconstruct_all_proposal_states()


@router.get("/reconstruct/proposals/consistency")
def proposal_consistency() -> dict[str, Any]:
    return reconstruction_service.proposal_consistency_health()


@router.get("/reconstruct/proposals/{proposal_id}")
def reconstruct_proposal(proposal_id: str) -> dict[str, Any]:
    return reconstruction_service.reconstruct_proposal_state(proposal_id)


@router.get("/reconstruct/proposals/{proposal_id}/compare")
def compare_proposal(proposal_id: str) -> dict[str, Any]:
    try:
        return reconstruction_service.compare_proposal_record_to_events(proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
