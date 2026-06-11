from collections.abc import Callable
from datetime import UTC, datetime

from app.models.decision_projection import DecisionProjection
from app.models.planner import PlannerRecommendationStatus
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType
from app.models.session_decision_projection import SessionDecisionProjection
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.decision_projection_builder_service import (
    DecisionProjectionBuilderService,
    decision_projection_builder_service,
)
from app.services.event_service import EventService, event_service


SESSION_DECISION_PROJECTION_SOURCE = "session_decision_projection_builder"
SESSION_DECISION_PROJECTION_SCHEMA_VERSION = 1
SESSION_DECISION_PROJECTION_TYPE = "session_decision_projection"


class SessionDecisionProjectionBuilderService(
    BaseProjectionBuilder[str, SessionDecisionProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=SESSION_DECISION_PROJECTION_TYPE,
        schema_version=SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
        builder_name="SessionDecisionProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=SESSION_DECISION_PROJECTION_TYPE,
            reconstruction_source="decision_projection",
            authoritative_source="runtime_session",
        ),
    )
    projection_type = SESSION_DECISION_PROJECTION_TYPE

    def __init__(
        self,
        projections: DecisionProjectionBuilderService | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._projections = projections or decision_projection_builder_service
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(self, session_id: str) -> SessionDecisionProjection:
        projections = self._projections.build(session_id)
        result = SessionDecisionProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=self._clock(),
                source=SESSION_DECISION_PROJECTION_SOURCE,
            ),
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
