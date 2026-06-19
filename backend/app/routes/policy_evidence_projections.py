from fastapi import APIRouter, HTTPException

from app.models.policy_evidence_projection import PolicyEvidenceProjection
from app.services.policy_evidence_projection_service import (
    PolicyEvidenceNotFoundError,
    policy_evidence_projection_service,
)


router = APIRouter()


@router.get("/runtime/policy-evidence")
def list_policy_evidence(
    policy_id: str | None = None,
    evaluation_id: str | None = None,
    evaluation_result_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    evidence_type: str | None = None,
) -> list[PolicyEvidenceProjection]:
    return policy_evidence_projection_service.list_policy_evidence(
        policy_id=policy_id,
        evaluation_id=evaluation_id,
        evaluation_result_id=evaluation_result_id,
        target_type=target_type,
        target_id=target_id,
        evidence_type=evidence_type,
    )


@router.get("/runtime/policy-evidence/{policy_id}")
def get_policy_evidence(policy_id: str) -> PolicyEvidenceProjection:
    try:
        return policy_evidence_projection_service.get_policy_evidence(policy_id)
    except PolicyEvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
