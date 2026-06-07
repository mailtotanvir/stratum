from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.cognitive_state import CognitiveState
from app.services.cognitive_state_service import cognitive_state_service
from app.services.proposal_service import ProposalNotFoundError
from app.services.reconstruction_service import reconstruction_service
from app.services.runtime_session_service import RuntimeSessionNotFoundError
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


@router.get("/reconstruct/planner-recommendations")
def reconstruct_planner_recommendations(
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    return reconstruction_service.get_reconstructed_recommendations(
        session_id=session_id
    )


@router.get("/reconstruct/planner-recommendations/consistency")
def planner_recommendation_consistency() -> dict[str, Any]:
    return reconstruction_service.recommendation_consistency_health()


@router.get("/reconstruct/planner-recommendations/{recommendation_id}")
def planner_recommendation_lineage(recommendation_id: str) -> dict[str, Any]:
    return reconstruction_service.get_recommendation_lineage(recommendation_id)


@router.get("/reconstruct/decision-records")
def reconstruct_decision_records(
    session_id: str | None = None,
) -> dict[str, Any]:
    return reconstruction_service.reconstruct_decision_records(
        session_id=session_id
    )


@router.get("/reconstruct/decision-evidence")
def reconstruct_decision_evidence(
    decision_id: str | None = None,
) -> dict[str, Any]:
    return reconstruction_service.reconstruct_decision_evidence(
        decision_id=decision_id
    )


@router.get("/reconstruct/decision-trails")
def reconstruct_decision_trails() -> list[dict[str, Any]]:
    return reconstruction_service.reconstruct_all_decision_trails()


@router.get("/reconstruct/decision-trails/{proposal_id}")
def reconstruct_decision_trail(proposal_id: str) -> dict[str, Any]:
    return reconstruction_service.reconstruct_decision_trail(proposal_id)


@router.get("/reconstruct/cognitive-state/{session_id}")
def reconstruct_cognitive_state(session_id: str) -> CognitiveState:
    try:
        return cognitive_state_service.reconstruct(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
