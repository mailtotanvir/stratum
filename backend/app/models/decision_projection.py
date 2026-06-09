from pydantic import BaseModel

from app.models.planner import PlannerRecommendationStatus


class DecisionProjection(BaseModel):
    decision_id: str
    recommendation_id: str
    status: PlannerRecommendationStatus
    selected_at: str
    evidence_count: int
    trail_entry_count: int
