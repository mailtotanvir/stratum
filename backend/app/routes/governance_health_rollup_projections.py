from fastapi import APIRouter

from app.models.governance_health_rollup_projection import (
    GovernanceHealthRollupProjection,
)
from app.services.governance_health_rollup_projection_builder_service import (
    governance_health_rollup_projection_builder_service,
)


router = APIRouter()


@router.get("/runtime/governance-health-rollup")
def get_governance_health_rollup() -> GovernanceHealthRollupProjection:
    return governance_health_rollup_projection_builder_service.build()
