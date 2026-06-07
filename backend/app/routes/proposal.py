from fastapi import APIRouter, HTTPException

from app.db.schema import ArtifactRecord, ProposalArtifactLinkRecord, ProposalRecord
from app.models.artifact import Artifact
from app.models.decision_trail import DecisionTrail
from app.models.proposal import Proposal, ProposalCreate, ProposalRespond
from app.models.proposal_artifact import ProposalArtifact, ProposalArtifactAttachment
from app.services.artifact_service import ArtifactNotFoundError, artifact_service
from app.services.event_service import event_service
from app.services.decision_trail_service import decision_trail_service
from app.services.proposal_artifact_service import (
    ProposalArtifactAlreadyAttachedError,
    proposal_artifact_service,
)
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
        source_type=record.source_type,
        source_id=record.source_id,
        source_context_snapshot=proposal_service.source_context_snapshot_for(record),
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


def to_artifact(record: ArtifactRecord) -> Artifact:
    return Artifact(
        id=record.id,
        task_id=record.task_id,
        proposal_id=record.proposal_id,
        path=record.path,
        kind=record.kind,
        created_at=record.created_at.isoformat(),
        metadata=artifact_service.metadata_for(record),
    )


def to_proposal_artifact(record: ProposalArtifactLinkRecord) -> ProposalArtifact:
    return ProposalArtifact(
        proposal_id=record.proposal_id,
        artifact_id=record.artifact_id,
        attached_at=record.created_at.isoformat(),
        artifact=to_artifact(artifact_service.get_artifact(record.artifact_id)),
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


@router.get("/proposals/{proposal_id}/decision-trail")
def proposal_decision_trail(proposal_id: str) -> DecisionTrail:
    try:
        proposal_service.get_proposal(proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return decision_trail_service.reconstruct(proposal_id)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str) -> Proposal:
    try:
        return to_proposal(proposal_service.get_proposal(proposal_id))
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/artifacts/{artifact_id}")
def attach_proposal_artifact(
    proposal_id: str,
    artifact_id: str,
) -> ProposalArtifactAttachment:
    try:
        proposal_artifact_service.attach_artifact(
            proposal_id=proposal_id,
            artifact_id=artifact_id,
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProposalArtifactAlreadyAttachedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ProposalArtifactAttachment(
        proposal_id=proposal_id,
        artifact_id=artifact_id,
        attached=True,
    )


@router.get("/proposals/{proposal_id}/artifacts")
def list_proposal_artifacts(proposal_id: str) -> list[ProposalArtifact]:
    try:
        proposal_service.get_proposal(proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        to_proposal_artifact(record)
        for record in proposal_artifact_service.list_proposal_artifacts(proposal_id)
    ]


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
