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
