from datetime import datetime

from pydantic import BaseModel


class EvaluationProjectionDiagnostics(BaseModel):
    projection_type: str
    registered: bool
    rebuildable: bool
    persisted: bool
    source: str
    route: str


class EvaluationDiagnostics(BaseModel):
    evaluation_count: int
    result_count: int
    dimension_count: int
    target_snapshot_count: int
    evaluations_without_results_count: int
    evaluations_without_target_snapshot_count: int
    registered_projection_types: list[str]
    projections: list[EvaluationProjectionDiagnostics]
    generated_at: datetime
