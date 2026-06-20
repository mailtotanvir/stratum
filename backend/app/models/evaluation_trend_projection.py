from datetime import datetime

from pydantic import BaseModel

from app.models.projection import Projection


class EvaluationTrendDimensionBucket(BaseModel):
    dimension_id: str
    dimension_name: str
    result_count: int
    average_score: float | None = None
    min_score: float | None = None
    max_score: float | None = None


class EvaluationTrendBucket(Projection):
    bucket_start: str
    bucket_end: str
    bucket_granularity: str
    evaluation_count: int
    result_count: int
    average_score: float | None = None
    min_score: float | None = None
    max_score: float | None = None
    target_types: list[str]
    evaluation_types: list[str]
    dimensions: list[EvaluationTrendDimensionBucket]


class EvaluationTrendOutcomeBucket(BaseModel):
    bucket_start: str
    bucket_end: str
    total_evaluations: int
    evaluations_by_outcome: dict[str, int]
    success_rate: float
    failure_rate: float
    acceptance_rate: float
    rejection_rate: float
    reversion_rate: float
    inconclusive_rate: float


class EvaluationTrendProjection(Projection):
    bucket_granularity: str
    buckets: list[EvaluationTrendOutcomeBucket]
    generated_at: datetime
