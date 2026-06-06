from typing import Any

from pydantic import BaseModel, Field

from app.models.tool import Tool


class PlanningProposalSummary(BaseModel):
    id: str
    title: str
    status: str
    source_type: str
    source_id: str | None = None
    created_at: str


class PlanningRecommendationSummary(BaseModel):
    id: str
    objective: str
    proposed_tool: dict[str, Any] | None = None
    rationale: str
    confidence: float
    governance_status: str
    created_at: str


class PlanningEventSummary(BaseModel):
    id: int
    timestamp: str
    type: str
    severity: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanningDiagnosticsSummary(BaseModel):
    proposal_count: int
    recommendation_count: int
    available_tool_count: int
    event_count: int
    latest_event_type: str | None = None
    governance_status: str
    highest_severity: str | None = None
    has_critical: bool


class PlanningContext(BaseModel):
    session_id: str
    task_id: str
    active_proposals: list[PlanningProposalSummary]
    active_recommendations: list[PlanningRecommendationSummary]
    available_tools: list[Tool]
    recent_events: list[PlanningEventSummary]
    diagnostics_summary: PlanningDiagnosticsSummary
