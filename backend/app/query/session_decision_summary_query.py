from typing import Any

from app.models.runtime_query import RuntimeQuery
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.decision_trail_service import (
    DecisionTrailService,
    decision_trail_service,
)
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


SESSION_DECISION_SUMMARY_QUERY_NAME = "session_decision_summary"


class SessionDecisionSummaryQuery:
    def __init__(
        self,
        sessions: RuntimeSessionService | None = None,
        decisions: DecisionRecordService | None = None,
        recommendations: PlannerRecommendationService | None = None,
        trails: DecisionTrailService | None = None,
    ) -> None:
        self._sessions = sessions or runtime_session_service
        self._decisions = decisions or decision_record_service
        self._recommendations = recommendations or planner_recommendation_service
        self._trails = trails or decision_trail_service

    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name=SESSION_DECISION_SUMMARY_QUERY_NAME,
            query_version=1,
            description=(
                "Summarize decisions, selected recommendations, and decision "
                "trails for a runtime session."
            ),
            query_type="session_query",
            supported_parameters={
                "session_id": {
                    "type": "string",
                    "required": True,
                    "description": "Runtime session identifier.",
                }
            },
            result_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "decision_count": {"type": "integer"},
                    "selected_recommendations": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "decision_trail_summary": {"type": "object"},
                },
                "required": [
                    "session_id",
                    "decision_count",
                    "selected_recommendations",
                    "decision_trail_summary",
                ],
            },
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        session_id = parameters.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError(
                "Runtime query parameter is required: session_id"
            )

        session = self._sessions.get_session(session_id)
        decisions = self._decisions.list_decision_records(session.id)
        recommendation_by_id = {
            recommendation.id: recommendation
            for recommendation in self._recommendations.list_recommendations(
                session.id
            )
        }
        selected_recommendations = []
        for decision in decisions:
            recommendation = recommendation_by_id.get(
                decision.selected_entity_id
            )
            selected_recommendations.append(
                {
                    "decision_id": decision.decision_id,
                    "recommendation_id": decision.selected_entity_id,
                    "status": (
                        recommendation.status
                        if recommendation is not None
                        else None
                    ),
                    "objective": (
                        recommendation.objective
                        if recommendation is not None
                        else None
                    ),
                }
            )

        decision_ids = {decision.decision_id for decision in decisions}
        recommendation_ids = {
            decision.selected_entity_id for decision in decisions
        }
        trails = [
            trail
            for trail in self._trails.reconstruct_all()
            if trail.decision_id in decision_ids
            or trail.recommendation_id in recommendation_ids
        ]
        trails.sort(
            key=lambda trail: (
                trail.created_at or "",
                trail.proposal_id,
            )
        )

        return {
            "session_id": session.id,
            "decision_count": len(decisions),
            "selected_recommendations": selected_recommendations,
            "decision_trail_summary": {
                "trail_count": len(trails),
                "decision_ids": sorted(
                    {
                        trail.decision_id
                        for trail in trails
                        if trail.decision_id is not None
                    }
                ),
                "evidence_count": sum(
                    len(trail.evidence_ids) for trail in trails
                ),
                "trails": [
                    trail.model_dump(mode="json")
                    for trail in trails
                ],
            },
        }


session_decision_summary_query = SessionDecisionSummaryQuery()
