from pydantic import BaseModel

from app.models.projection import Projection


class EvaluationOutcomeDimensionRollup(BaseModel):
    dimension_id: str
    dimension_name: str
    evaluation_count: int
    result_count: int
    average_score: float | None = None
    latest_score: float | None = None
    latest_evaluated_at: str | None = None


class EvaluationOutcomeRollup(Projection):
    target_type: str
    target_id: str
    target_summary: str
    evaluation_count: int
    result_count: int
    average_score: float | None = None
    min_score: float | None = None
    max_score: float | None = None
    latest_evaluation_id: str | None = None
    latest_evaluation_status: str | None = None
    latest_evaluated_at: str | None = None
    dimensions: list[EvaluationOutcomeDimensionRollup]
    updated_at: str
