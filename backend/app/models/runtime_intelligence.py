from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RuntimeIntelligenceStatus = Literal[
    "healthy",
    "warning",
    "degraded",
    "unhealthy",
]
RuntimeRiskLevel = Literal["low", "moderate", "high", "critical"]
RuntimeRiskSeverity = Literal["moderate", "high", "critical"]


class RuntimeRisk(BaseModel):
    risk_id: str = Field(min_length=1)
    severity: RuntimeRiskSeverity
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence_count: int = Field(ge=1)


class RuntimeRiskSummary(BaseModel):
    generated_at: datetime
    risk_level: RuntimeRiskLevel
    notable_risks: list[RuntimeRisk]
    risk_count: int = Field(ge=0)
    recommended_operator_attention: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class RuntimeActivityItem(BaseModel):
    event_id: int = Field(ge=1)
    occurred_at: datetime
    event_type: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    signal: str = Field(min_length=1)


class RuntimeActivitySummary(BaseModel):
    generated_at: datetime
    recent_activity: list[RuntimeActivityItem]
    high_signal_event_count: int = Field(ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class RuntimeIntegritySummary(BaseModel):
    generated_at: datetime
    projection_integrity_status: RuntimeIntelligenceStatus
    reconstruction_status: RuntimeIntelligenceStatus
    drift_detections: int = Field(ge=0)
    projection_failures: int = Field(ge=0)
    failed_rebuilds: int = Field(ge=0)
    failed_replays: int = Field(ge=0)
    stale_projection_rebuilds: int = Field(ge=0)
    incomplete_lineage_or_reconstructions: int = Field(ge=0)
    reconstruction_failures: int = Field(ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class RuntimeGovernanceIntelligenceSummary(BaseModel):
    generated_at: datetime
    governance_status: RuntimeIntelligenceStatus
    approvals: int = Field(ge=0)
    rejections: int = Field(ge=0)
    rejection_rate: float = Field(ge=0)
    governance_activity_rate: float = Field(ge=0)
    rejection_spike_detected: bool
    recommended_operator_attention: list[str] = Field(default_factory=list)


class RuntimeIntelligenceSummary(BaseModel):
    generated_at: datetime
    overall_status: RuntimeIntelligenceStatus
    health_status: RuntimeIntelligenceStatus
    projection_integrity_status: RuntimeIntelligenceStatus
    governance_status: RuntimeIntelligenceStatus
    reconstruction_status: RuntimeIntelligenceStatus
    risk_level: RuntimeRiskLevel
    notable_risks: list[RuntimeRisk]
    recent_activity: list[RuntimeActivityItem]
    recommended_operator_attention: list[str] = Field(default_factory=list)
    risk_summary: RuntimeRiskSummary
    activity_summary: RuntimeActivitySummary
    integrity_summary: RuntimeIntegritySummary
    governance_summary: RuntimeGovernanceIntelligenceSummary
    incomplete: bool = False
    incomplete_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
