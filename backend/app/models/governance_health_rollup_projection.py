from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.projection import Projection


GovernanceHealthStatus = Literal["healthy", "watch", "degraded", "unknown"]


class GovernanceHealthRollupProjection(Projection):
    total_evaluations: int = Field(ge=0)
    overall_success_rate: float = Field(ge=0)
    overall_failure_rate: float = Field(ge=0)
    overall_rejection_rate: float = Field(ge=0)
    overall_reversion_rate: float = Field(ge=0)
    average_evaluation_score: float | None = None
    recommendation_success_rate: float = Field(ge=0)
    decision_success_rate: float = Field(ge=0)
    decision_evaluation_coverage_rate: float = Field(ge=0)
    policy_success_rate: float = Field(ge=0)
    health_status: GovernanceHealthStatus
    health_reasons: list[str] = Field(default_factory=list)
    generated_at: datetime
