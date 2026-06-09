from app.models.decision_projection import DecisionProjection
from app.models.planner import PlannerRecommendationStatus
from app.models.runtime_event import EventType
from app.models.session_decision_projection import SessionDecisionProjection
from app.services.decision_projection_builder_service import (
    DecisionProjectionBuilderService,
    decision_projection_builder_service,
)
from app.services.event_service import EventService, event_service


SESSION_DECISION_PROJECTION_SOURCE = "session_decision_projection_builder"


class SessionDecisionProjectionBuilderService:
    def __init__(
        self,
        projections: DecisionProjectionBuilderService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._projections = projections or decision_projection_builder_service
        self._events = events or event_service

    def build(self, session_id: str) -> SessionDecisionProjection:
        projections = self._projections.build(session_id)
        result = SessionDecisionProjection(
            session_id=session_id,
            projection_count=len(projections),
            selected_decision_count=self._count_status(
                projections,
                PlannerRecommendationStatus.PROMOTED,
            ),
            pending_decision_count=self._count_status(
                projections,
                PlannerRecommendationStatus.ACTIVE,
            ),
            rejected_decision_count=self._count_status(
                projections,
                PlannerRecommendationStatus.DISMISSED,
            ),
            projections=projections,
        )

        self._events.emit_event_sync(
            event_type=EventType.SESSION_DECISION_PROJECTION_BUILT,
            message=f"Session decision projection built: {session_id}",
            metadata={
                "session_id": session_id,
                "projection_count": result.projection_count,
                "source": SESSION_DECISION_PROJECTION_SOURCE,
            },
        )
        return result

    def _count_status(
        self,
        projections: list[DecisionProjection],
        status: PlannerRecommendationStatus,
    ) -> int:
        return sum(1 for projection in projections if projection.status == status)


session_decision_projection_builder_service = (
    SessionDecisionProjectionBuilderService()
)
