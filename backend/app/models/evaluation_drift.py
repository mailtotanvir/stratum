from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.projection import Projection


EvaluationDriftStatus = Literal["regressed", "improved", "unchanged"]


class EvaluationDriftBaselineCreate(BaseModel):
    baseline_id: str | None = Field(default=None, min_length=1)
    evaluation_id: str = Field(min_length=1)
    evaluation_name: str = Field(min_length=1)
    evaluation_version: int = Field(ge=1)
    baseline_score: float
    baseline_pass_count: int = Field(ge=0)
    baseline_fail_count: int = Field(ge=0)


class EvaluationDriftBaseline(EvaluationDriftBaselineCreate):
    baseline_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationDriftObservationCreate(BaseModel):
    observation_id: str | None = Field(default=None, min_length=1)
    evaluation_id: str = Field(min_length=1)
    evaluation_name: str = Field(min_length=1)
    evaluation_version: int = Field(ge=1)
    observed_score: float
    observed_pass_count: int = Field(ge=0)
    observed_fail_count: int = Field(ge=0)


class EvaluationDriftObservation(EvaluationDriftObservationCreate):
    observation_id: str = Field(min_length=1)
    observed_at: datetime


class EvaluationDriftRecord(BaseModel):
    drift_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    evaluation_name: str = Field(min_length=1)
    evaluation_version: int = Field(ge=1)
    baseline_score: float
    observed_score: float
    score_delta: float
    baseline_pass_count: int = Field(ge=0)
    observed_pass_count: int = Field(ge=0)
    baseline_fail_count: int = Field(ge=0)
    observed_fail_count: int = Field(ge=0)
    drift_status: EvaluationDriftStatus


class EvaluationDriftProjection(Projection):
    baselines: list[EvaluationDriftBaseline] = Field(default_factory=list)
    observations: list[EvaluationDriftObservation] = Field(default_factory=list)
    drift_records: list[EvaluationDriftRecord] = Field(default_factory=list)
    total_baselines: int = Field(ge=0)
    total_observations: int = Field(ge=0)
    total_drift_records: int = Field(ge=0)
    regressed_count: int = Field(ge=0)
    improved_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    generated_at: datetime
