from pydantic import BaseModel

from app.models.decision_projection import DecisionProjection


class SessionDecisionProjection(BaseModel):
    session_id: str
    projection_count: int
    selected_decision_count: int
    pending_decision_count: int
    rejected_decision_count: int
    projections: list[DecisionProjection]
