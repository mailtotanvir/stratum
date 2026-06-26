from datetime import datetime

from pydantic import BaseModel, Field

from app.models.projection import Projection


class EvaluationLineageRecordCreate(BaseModel):
    lineage_id: str | None = Field(default=None, min_length=1)
    evaluation_id: str = Field(min_length=1)
    evaluation_name: str = Field(min_length=1)
    evaluation_version: int = Field(ge=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_category: str = Field(min_length=1)


class EvaluationLineageRecord(EvaluationLineageRecordCreate):
    lineage_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationEvidenceRecordCreate(BaseModel):
    evidence_id: str | None = Field(default=None, min_length=1)
    lineage_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    description: str = Field(min_length=1)


class EvaluationEvidenceRecord(EvaluationEvidenceRecordCreate):
    evidence_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationLineageProjection(Projection):
    lineage_records: list[EvaluationLineageRecord] = Field(
        default_factory=list
    )
    evidence_records: list[EvaluationEvidenceRecord] = Field(
        default_factory=list
    )
    total_lineage_records: int = Field(ge=0)
    total_evidence_records: int = Field(ge=0)
    generated_at: datetime
