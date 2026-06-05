from typing import Any

from pydantic import BaseModel, Field

from app.models.proposal import Proposal
from app.models.tool import Tool


class PlannerRequest(BaseModel):
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    available_tools: list[Tool]
    context: dict[str, Any] = Field(default_factory=dict)


class PlannerPreviewRequest(BaseModel):
    objective: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class PlannerResponse(BaseModel):
    proposed_tool: Tool | None = None
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlannerProposalResponse(BaseModel):
    proposal: Proposal
    planner_response: PlannerResponse


class PlannerProposalPreviewResponse(BaseModel):
    planner_response: PlannerResponse
    governance_preview: dict[str, Any]
    proposal_allowed: bool


class PlannerRecommendation(BaseModel):
    id: str
    task_id: str
    session_id: str
    objective: str
    proposed_tool: dict[str, Any] | None = None
    rationale: str
    confidence: float
    governance_status: str
    created_at: str


class PlannerRecommendationResponse(BaseModel):
    recommendation: PlannerRecommendation
    planner_response: PlannerResponse
    governance_preview: dict[str, Any]


class PlannerRecommendationPromotionResponse(BaseModel):
    proposal: Proposal
    recommendation: PlannerRecommendation
