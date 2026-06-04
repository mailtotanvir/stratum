from fastapi import APIRouter, HTTPException

from app.db.schema import ProposalRecord
from app.models.proposal import Proposal, ProposalCreate, ProposalRespond
from app.services.event_service import event_service
from app.services.proposal_service import (
    InvalidProposalDecisionError,
    ProposalAlreadyResolvedError,
    ProposalNotFoundError,
    proposal_service,
)

router = APIRouter()


def to_proposal(record: ProposalRecord) -> Proposal:
    return Proposal(
        id=record.id,
        task_id=record.task_id,
        title=record.title,
        body=record.body,
        status=record.status,
        created_at=record.created_at.isoformat(),
        resolved_at=(
            record.resolved_at.isoformat()
            if record.resolved_at is not None
            else None
        ),
        decision=record.decision,
    )


@router.post("/proposals")
def create_proposal(request: ProposalCreate) -> Proposal:
    return to_proposal(
        proposal_service.create_proposal(
            title=request.title,
            body=request.body,
            task_id=request.task_id,
        )
    )


@router.get("/proposals")
def list_proposals(
    status: str | None = None,
    task_id: str | None = None,
) -> list[Proposal]:
    return [
        to_proposal(proposal)
        for proposal in proposal_service.list_proposals(
            status=status,
            task_id=task_id,
        )
    ]


@router.get("/proposals/{proposal_id}/trace")
def proposal_trace(
    proposal_id: str,
    type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    return [
        event.to_dict()
        for event in event_service.list_persisted_events(
            event_type=type,
            proposal_id=proposal_id,
            limit=limit,
        )
    ]


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str) -> Proposal:
    try:
        return to_proposal(proposal_service.get_proposal(proposal_id))
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/respond")
def respond_to_proposal(
    proposal_id: str,
    request: ProposalRespond,
) -> Proposal:
    try:
        return to_proposal(
            proposal_service.respond(
                proposal_id=proposal_id,
                decision=request.decision.value,
            )
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProposalAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidProposalDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
