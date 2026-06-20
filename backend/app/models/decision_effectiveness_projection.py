from datetime import datetime

from pydantic import Field

from app.models.projection import Projection


class DecisionEffectivenessProjection(Projection):
    decision_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    evaluation_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    reverted_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    success_rate: float = Field(ge=0)
    failure_rate: float = Field(ge=0)
    average_score: float | None = None
    has_evaluation_coverage: bool
    generated_at: datetime
