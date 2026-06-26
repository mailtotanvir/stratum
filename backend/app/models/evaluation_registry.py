from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.projection import Projection


EvaluationDefinitionStatus = Literal["active", "draft", "retired"]


class EvaluationDefinitionCreate(BaseModel):
    evaluation_id: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: EvaluationDefinitionStatus = "active"


class EvaluationDefinition(EvaluationDefinitionCreate):
    evaluation_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationSuiteCreate(BaseModel):
    suite_id: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evaluation_ids: list[str] = Field(default_factory=list)


class EvaluationSuite(EvaluationSuiteCreate):
    suite_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationRegistryProjection(Projection):
    definitions: list[EvaluationDefinition] = Field(default_factory=list)
    suites: list[EvaluationSuite] = Field(default_factory=list)
    total_definitions: int = Field(ge=0)
    total_suites: int = Field(ge=0)
    generated_at: datetime
