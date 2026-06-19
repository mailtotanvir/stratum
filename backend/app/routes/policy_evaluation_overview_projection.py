from fastapi import APIRouter

from app.models.policy_evaluation_overview_projection import (
    PolicyEvaluationOverviewProjection,
)
from app.services.policy_evaluation_overview_projection_service import (
    policy_evaluation_overview_projection_service,
)


router = APIRouter()


@router.get("/runtime/policy-evaluation-overview")
def get_policy_evaluation_overview() -> PolicyEvaluationOverviewProjection:
    return (
        policy_evaluation_overview_projection_service
        .get_policy_evaluation_overview()
    )
