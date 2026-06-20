from datetime import datetime

from pydantic import Field

from app.models.projection import Projection


class RecommendationOutcomeProjection(Projection):
    recommendation_id: str = Field(min_length=1)
    recommendation_type: str = Field(min_length=1)
    recommendation_category: str = Field(min_length=1)
    selected_count: int = Field(ge=0)
    not_selected_count: int = Field(ge=0)
    evaluation_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    reverted_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    success_rate: float = Field(ge=0)
    average_score: float | None = None
    generated_at: datetime
