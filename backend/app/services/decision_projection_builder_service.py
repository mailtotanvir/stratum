from app.models.decision_projection import DecisionProjection
from app.models.runtime_event import EventType
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    decision_evidence_service,
)
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.decision_trail_service import (
    DecisionTrailService,
    decision_trail_service,
)
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


DECISION_PROJECTION_SOURCE = "decision_projection_builder"


class DecisionProjectionBuilderService:
    def __init__(
        self,
        sessions: RuntimeSessionService | None = None,
        decisions: DecisionRecordService | None = None,
        evidence: DecisionEvidenceService | None = None,
        trails: DecisionTrailService | None = None,
        recommendations: PlannerRecommendationService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._sessions = sessions or runtime_session_service
        self._decisions = decisions or decision_record_service
        self._evidence = evidence or decision_evidence_service
        self._trails = trails or decision_trail_service
        self._recommendations = recommendations or planner_recommendation_service
        self._events = events or event_service

    def build(self, session_id: str) -> list[DecisionProjection]:
        session = self._sessions.get_session(session_id)
        decisions = self._decisions.list_decision_records(session.id)
        decision_ids = {decision.decision_id for decision in decisions}
        evidence_counts = dict.fromkeys(decision_ids, 0)
        for record in self._evidence.list_evidence():
            if record.decision_id in evidence_counts:
                evidence_counts[record.decision_id] += 1

        trail_counts = dict.fromkeys(decision_ids, 0)
        for trail in self._trails.reconstruct_all():
            if trail.decision_id in trail_counts:
                trail_counts[trail.decision_id] += 1

        recommendation_statuses = {
            recommendation.id: recommendation.status
            for recommendation in self._recommendations.list_recommendations(
                session.id
            )
        }
        projections = [
            DecisionProjection(
                decision_id=decision.decision_id,
                recommendation_id=decision.selected_entity_id,
                status=recommendation_statuses[decision.selected_entity_id],
                selected_at=decision.created_at.isoformat(),
                evidence_count=evidence_counts[decision.decision_id],
                trail_entry_count=trail_counts[decision.decision_id],
            )
            for decision in decisions
        ]

        self._events.emit_event_sync(
            event_type=EventType.DECISION_PROJECTION_BUILT,
            message=f"Decision projections built: {session.id}",
            metadata={
                "session_id": session.id,
                "projection_count": len(projections),
                "source": DECISION_PROJECTION_SOURCE,
            },
        )
        return projections


decision_projection_builder_service = DecisionProjectionBuilderService()
