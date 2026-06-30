from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.projection import Projection


EvaluationAccountabilityTargetType = Literal[
    "provider_execution",
    "runtime_session",
    "tool_invocation",
    "external_agent_invocation",
    "execution_participant",
    "skill",
    "prompt",
    "repository_transformation",
    "artifact",
    "human_decision",
]

EvaluationRiskLevel = Literal["low", "medium", "high", "critical"]
EvaluationRunOutcome = Literal["pass", "fail", "inconclusive", "review"]


class EvaluationScenarioCreate(BaseModel):
    scenario_id: str | None = Field(default=None, min_length=1)
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_fixture: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    rubric: str = Field(min_length=1)
    target_type: EvaluationAccountabilityTargetType
    version: int = Field(ge=1)
    tags: list[str] = Field(default_factory=list)
    risk_level: EvaluationRiskLevel


class EvaluationScenario(EvaluationScenarioCreate):
    scenario_id: str = Field(min_length=1)
    created_at: datetime


class EvaluationRunCreate(BaseModel):
    run_id: str | None = Field(default=None, min_length=1)
    scenario_id: str = Field(min_length=1)
    target_type: EvaluationAccountabilityTargetType
    target_id: str = Field(min_length=1)
    target_runtime_event_id: int | None = None
    evaluator: str = Field(min_length=1)
    evaluator_type: str = Field(min_length=1)
    outcome: EvaluationRunOutcome
    score: float | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRun(EvaluationRunCreate):
    run_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    scenario_version: int


class AccountabilityScorecard(BaseModel):
    target_type: EvaluationAccountabilityTargetType
    target_id: str
    evaluation_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    average_score: float | None = None
    latest_run_id: str | None = None
    latest_outcome: EvaluationRunOutcome | None = None
    latest_evaluated_at: datetime | None = None


class RegressionFinding(BaseModel):
    target_type: EvaluationAccountabilityTargetType
    target_id: str
    baseline_run_id: str | None = None
    comparison_run_id: str | None = None
    baseline_score: float | None = None
    comparison_score: float | None = None
    score_delta: float | None = None
    status: str
    signature: str


class RegressionSummary(BaseModel):
    total_targets: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    regressed_count: int = Field(ge=0)
    improved_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    repeated_failure_signatures: list[dict[str, Any]] = Field(default_factory=list)
    quality_drift_indicators: list[str] = Field(default_factory=list)
    findings: list[RegressionFinding] = Field(default_factory=list)
    generated_at: datetime


class AccountabilityDecisionRecord(BaseModel):
    decision_id: str
    target_type: EvaluationAccountabilityTargetType
    target_id: str
    decision_summary: str
    runtime_event_id: int | None = None
    created_at: datetime


class AccountabilityDecisionCreate(BaseModel):
    decision_id: str = Field(min_length=1)
    target_type: EvaluationAccountabilityTargetType
    target_id: str = Field(min_length=1)
    decision_summary: str = Field(min_length=1)
    runtime_event_id: int | None = None


class EvaluationScenarioRegistryProjection(Projection):
    scenarios: list[EvaluationScenario] = Field(default_factory=list)
    total_scenarios: int = Field(ge=0)
    generated_at: datetime


class EvaluationAccountabilityProjection(Projection):
    scenarios: list[EvaluationScenario] = Field(default_factory=list)
    runs: list[EvaluationRun] = Field(default_factory=list)
    scorecards: list[AccountabilityScorecard] = Field(default_factory=list)
    regressions: RegressionSummary
    decisions: list[AccountabilityDecisionRecord] = Field(default_factory=list)
    generated_at: datetime
