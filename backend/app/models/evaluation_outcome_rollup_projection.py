from datetime import datetime

from pydantic import Field

from app.models.projection import Projection


class EvaluationOutcomeRollupProjection(Projection):
    total_evaluations: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    reverted_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    success_rate: float = Field(ge=0)
    failure_rate: float = Field(ge=0)
    acceptance_rate: float = Field(ge=0)
    rejection_rate: float = Field(ge=0)
    reversion_rate: float = Field(ge=0)
    inconclusive_rate: float = Field(ge=0)
    generated_at: datetime
