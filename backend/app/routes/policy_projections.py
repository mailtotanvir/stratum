from fastapi import APIRouter, HTTPException

from app.models.policy_projection import PolicySummaryProjection
from app.services.policy_projection_service import (
    PolicySummaryNotFoundError,
    policy_projection_service,
)


router = APIRouter()


@router.get("/runtime/policy-projections")
def list_policy_projections(
    policy_type: str | None = None,
    status: str | None = None,
) -> list[PolicySummaryProjection]:
    return policy_projection_service.list_policy_summaries(
        policy_type=policy_type,
        status=status,
    )


@router.get("/runtime/policy-projections/{policy_id}")
def get_policy_projection(policy_id: str) -> PolicySummaryProjection:
    try:
        return policy_projection_service.get_policy_summary(policy_id)
    except PolicySummaryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
