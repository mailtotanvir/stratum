from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


EvaluationTargetType = Literal[
    "recommendation",
    "decision",
    "artifact",
    "tool_invocation",
    "provider_usage",
    "runtime_session",
]

EvaluationOutcome = Literal[
    "success",
    "failure",
    "accepted",
    "rejected",
    "reverted",
    "inconclusive",
]


class EvaluationRecordCreate(BaseModel):
    session_id: str | None = None
    task_id: str | None = None
    target_type: EvaluationTargetType
    target_id: str = Field(min_length=1)
    evaluation_type: str = Field(min_length=1)
    outcome: EvaluationOutcome
    score: float | None = None
    evaluator: str = Field(min_length=1)
    rationale: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRecord(EvaluationRecordCreate):
    evaluation_id: str = Field(min_length=1)
    created_at: datetime
