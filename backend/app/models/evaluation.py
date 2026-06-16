from typing import Any

from pydantic import BaseModel, Field, model_validator


class EvaluationDimensionCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class EvaluationDimension(BaseModel):
    id: str
    name: str
    description: str
    created_at: str


class EvaluationCreate(BaseModel):
    session_id: str | None = None
    decision_id: str | None = None
    artifact_id: str | None = None
    evaluation_type: str = Field(min_length=1)
    status: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_reference(self) -> "EvaluationCreate":
        if not any([self.session_id, self.decision_id, self.artifact_id]):
            raise ValueError(
                "At least one reference is required: session_id, "
                "decision_id, or artifact_id"
            )
        return self


class Evaluation(BaseModel):
    id: str
    session_id: str | None = None
    decision_id: str | None = None
    artifact_id: str | None = None
    evaluation_type: str
    status: str
    created_at: str


class EvaluationTargetSnapshot(BaseModel):
    evaluation_id: str
    target_type: str
    target_id: str
    target_summary: str
    target_metadata: dict[str, Any] | None = None
    created_at: str


class EvaluationResultCreate(BaseModel):
    dimension_id: str = Field(min_length=1)
    score: float
    rationale: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None


class EvaluationResult(BaseModel):
    id: str
    evaluation_id: str
    dimension_id: str
    score: float
    rationale: str
    metadata: dict[str, Any] | None = None
    created_at: str


class EvaluationDetail(Evaluation):
    target_snapshot: EvaluationTargetSnapshot | None = None
    results: list[EvaluationResult] = Field(default_factory=list)
