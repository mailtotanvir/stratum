from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


EvaluationDependencyStatus = Literal["healthy", "unhealthy"]
EvaluationHealthStatus = Literal["healthy", "unhealthy"]


class EvaluationProjectionDiagnostic(BaseModel):
    projection_name: str
    projection_type: str
    registered: bool
    rebuild_supported: bool
    rebuildable: bool
    persisted: bool
    source: str
    route: str
    dependency_count: int = Field(ge=0)
    dependency_status: EvaluationDependencyStatus
    record_count: int = Field(ge=0)
    health_status: EvaluationHealthStatus
    reconstruction_status: str = Field(min_length=1)
    replay_verified: bool


EvaluationProjectionDiagnostics = EvaluationProjectionDiagnostic


class EvaluationDiagnosticsProjection(BaseModel):
    projections: list[EvaluationProjectionDiagnostic]
    total_projections: int = Field(ge=0)
    healthy_projections: int = Field(ge=0)
    unhealthy_projections: int = Field(ge=0)
    rebuildable_projections: int = Field(ge=0)
    dependency_failures: int = Field(ge=0)
    overall_health: EvaluationHealthStatus
    generated_at: datetime


class EvaluationDiagnostics(BaseModel):
    evaluation_count: int
    result_count: int
    dimension_count: int
    target_snapshot_count: int
    evaluations_without_results_count: int
    evaluations_without_target_snapshot_count: int
    registered_projection_types: list[str]
    projections: list[EvaluationProjectionDiagnostic]
    total_projections: int = Field(ge=0)
    healthy_projections: int = Field(ge=0)
    unhealthy_projections: int = Field(ge=0)
    rebuildable_projections: int = Field(ge=0)
    dependency_failures: int = Field(ge=0)
    overall_health: EvaluationHealthStatus
    generated_at: datetime
