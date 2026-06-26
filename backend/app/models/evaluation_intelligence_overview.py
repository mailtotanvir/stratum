from datetime import datetime

from pydantic import Field

from app.models.projection import Projection


class EvaluationIntelligenceOverviewProjection(Projection):
    total_evaluations: int = Field(ge=0)
    total_suites: int = Field(ge=0)
    total_coverage_targets: int = Field(ge=0)
    covered_targets: int = Field(ge=0)
    uncovered_targets: int = Field(ge=0)
    coverage_percentage: float = Field(ge=0)
    total_lineage_records: int = Field(ge=0)
    total_evidence_records: int = Field(ge=0)
    total_drift_records: int = Field(ge=0)
    regressed_count: int = Field(ge=0)
    improved_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    healthy_evaluations: int = Field(ge=0)
    regressing_evaluations: int = Field(ge=0)
    generated_at: datetime
