from datetime import date, datetime

from pydantic import BaseModel, Field


class GovernanceAnalytics(BaseModel):
    approvals: int = Field(ge=0)
    rejections: int = Field(ge=0)
    policy_evaluations: int = Field(ge=0)
    reflection_triggers: int = Field(ge=0)
    budget_actions: int = Field(ge=0)
    governance_activity_rate: float = Field(ge=0)


class ProjectionAnalytics(BaseModel):
    registered_projections: int = Field(ge=0)
    projection_rebuilds: int = Field(ge=0)
    projection_replays: int = Field(ge=0)
    drift_checks: int = Field(ge=0)
    drift_detections: int = Field(ge=0)
    projection_failures: int = Field(ge=0)


class ReconstructionAnalytics(BaseModel):
    reconstructed_sessions: int = Field(ge=0)
    reconstruction_failures: int = Field(ge=0)
    incomplete_reconstructions: int = Field(ge=0)
    average_reconstruction_duration_ms: float = Field(ge=0)


class RuntimeTrendBucket(BaseModel):
    day: date
    events: int = Field(ge=0)
    decisions: int = Field(ge=0)
    artifacts: int = Field(ge=0)
    governance_actions: int = Field(ge=0)


class RuntimeTrendAnalytics(BaseModel):
    lookback_days: int = Field(ge=1)
    buckets: list[RuntimeTrendBucket]
    events_per_day: dict[str, int]
    decisions_per_day: dict[str, int]
    artifacts_per_day: dict[str, int]
    governance_actions_per_day: dict[str, int]


class RuntimeOperationalAnalytics(BaseModel):
    generated_at: datetime
    total_sessions: int = Field(ge=0)
    active_sessions: int = Field(ge=0)
    completed_sessions: int = Field(ge=0)
    failed_sessions: int = Field(ge=0)
    total_events: int = Field(ge=0)
    total_proposals: int = Field(ge=0)
    total_decisions: int = Field(ge=0)
    total_artifacts: int = Field(ge=0)
    total_tool_executions: int = Field(ge=0)
    governance: GovernanceAnalytics
    projections: ProjectionAnalytics
    reconstruction: ReconstructionAnalytics
    trends: RuntimeTrendAnalytics
    incomplete: bool = False
    incomplete_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
