from typing import Any

from pydantic import BaseModel, Field


class PolicyCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    policy_type: str = Field(min_length=1)
    status: str = Field(min_length=1)


class PolicyVersionCreate(BaseModel):
    version: int = Field(ge=1)
    rule_payload: dict[str, Any]


class PolicyDecisionCreate(BaseModel):
    policy_version_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evaluation_id: str | None = None
    evaluation_result_id: str | None = None
    metadata: dict[str, Any] | None = None


class PolicyViolationCreate(BaseModel):
    policy_version_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evaluation_id: str | None = None
    evaluation_result_id: str | None = None
    metadata: dict[str, Any] | None = None


class PolicyVersion(BaseModel):
    id: str
    policy_id: str
    version: int
    rule_payload: dict[str, Any]
    created_at: str


class PolicyDecision(BaseModel):
    id: str
    policy_id: str
    policy_version_id: str
    target_type: str
    target_id: str
    decision: str
    reason: str
    evaluation_id: str | None = None
    evaluation_result_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str


class PolicyViolation(BaseModel):
    id: str
    policy_id: str
    policy_version_id: str
    target_type: str
    target_id: str
    severity: str
    message: str
    evaluation_id: str | None = None
    evaluation_result_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str


class Policy(BaseModel):
    id: str
    name: str
    description: str
    policy_type: str
    status: str
    created_at: str
    updated_at: str


class PolicyDetail(Policy):
    versions: list[PolicyVersion] = Field(default_factory=list)
    decisions: list[PolicyDecision] = Field(default_factory=list)
    violations: list[PolicyViolation] = Field(default_factory=list)
