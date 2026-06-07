from enum import StrEnum

from pydantic import BaseModel


class CognitiveHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class CognitiveState(BaseModel):
    session_id: str
    task_id: str
    active_recommendation_count: int
    promoted_recommendation_count: int
    dismissed_recommendation_count: int
    active_proposal_count: int
    decision_record_count: int
    decision_evidence_count: int
    latest_recommendation_id: str | None = None
    latest_decision_id: str | None = None
    latest_proposal_id: str | None = None
    available_tool_count: int
    cognitive_health: CognitiveHealth
