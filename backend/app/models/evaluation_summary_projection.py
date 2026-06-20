from datetime import datetime

from pydantic import Field

from app.models.projection import Projection


class EvaluationSummaryProjection(Projection):
    total_evaluations: int = Field(ge=0)
    evaluations_by_type: dict[str, int] = Field(default_factory=dict)
    evaluations_by_outcome: dict[str, int] = Field(default_factory=dict)
    evaluations_by_target_type: dict[str, int] = Field(default_factory=dict)
    average_score_by_evaluation_type: dict[str, float] = Field(
        default_factory=dict
    )
    average_score_by_target_type: dict[str, float] = Field(
        default_factory=dict
    )
    generated_at: datetime
