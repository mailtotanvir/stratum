from app.models.decision_projection import DecisionProjection
from app.models.projection import Projection


class SessionDecisionProjection(Projection):
    session_id: str
    projection_count: int
    selected_decision_count: int
    pending_decision_count: int
    rejected_decision_count: int
    projections: list[DecisionProjection]
