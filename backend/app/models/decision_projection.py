from app.models.planner import PlannerRecommendationStatus
from app.models.projection import Projection


class DecisionProjection(Projection):
    decision_id: str
    recommendation_id: str
    status: PlannerRecommendationStatus
    selected_at: str
    evidence_count: int
    trail_entry_count: int
