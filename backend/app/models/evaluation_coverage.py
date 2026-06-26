from datetime import datetime

from pydantic import BaseModel, Field

from app.models.projection import Projection


class CoverageTargetCreate(BaseModel):
    target_id: str | None = Field(default=None, min_length=1)
    target_name: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_category: str = Field(min_length=1)
    description: str = Field(min_length=1)


class CoverageTarget(CoverageTargetCreate):
    target_id: str = Field(min_length=1)
    created_at: datetime


class CoverageMappingCreate(BaseModel):
    mapping_id: str | None = Field(default=None, min_length=1)
    target_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    evaluation_name: str = Field(min_length=1)
    evaluation_version: int = Field(ge=1)


class CoverageMapping(CoverageMappingCreate):
    mapping_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationCoverageProjection(Projection):
    targets: list[CoverageTarget] = Field(default_factory=list)
    mappings: list[CoverageMapping] = Field(default_factory=list)
    covered_targets: list[CoverageTarget] = Field(default_factory=list)
    uncovered_targets: list[CoverageTarget] = Field(default_factory=list)
    total_targets: int = Field(ge=0)
    coverage_percentage: float = Field(ge=0)
    generated_at: datetime
