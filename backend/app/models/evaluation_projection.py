from pydantic import BaseModel

from app.models.projection import Projection


class EvaluationDimensionSummary(BaseModel):
    dimension_id: str
    dimension_name: str
    result_count: int
    average_score: float | None = None
    latest_score: float | None = None


class EvaluationSummaryProjection(Projection):
    evaluation_id: str
    session_id: str | None = None
    decision_id: str | None = None
    artifact_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    target_summary: str | None = None
    evaluation_type: str
    status: str
    result_count: int
    average_score: float | None = None
    min_score: float | None = None
    max_score: float | None = None
    dimensions: list[EvaluationDimensionSummary]
    created_at: str
    updated_at: str


class EvaluationProjection(Projection):
    total_evaluations: int
    evaluations_by_type: dict[str, int]
    evaluations_by_outcome: dict[str, int]
    evaluations_by_target_type: dict[str, int]
    average_score_by_evaluation_type: dict[str, float]
    average_score_by_target_type: dict[str, float]
