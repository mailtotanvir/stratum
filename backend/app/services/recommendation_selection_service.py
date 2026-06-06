from datetime import UTC, datetime

from app.models.planner import (
    PlannerRecommendationStatus,
    RankedPlannerRecommendation,
    RecommendationSelectionPreview,
)
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)


GOVERNANCE_STATUS_RANK = {
    "ok": 2,
    "degraded": 1,
    "critical": 0,
}


class RecommendationSelectionService:
    def __init__(
        self,
        recommendations: PlannerRecommendationService | None = None,
    ) -> None:
        self._recommendations = recommendations or planner_recommendation_service

    def preview(self, session_id: str) -> RecommendationSelectionPreview:
        records = self._recommendations.list_recommendations(
            session_id=session_id,
            status=PlannerRecommendationStatus.ACTIVE.value,
        )
        ranked_records = sorted(records, key=self._ranking_key)
        ranked_recommendations = [
            RankedPlannerRecommendation(
                recommendation_id=record.id,
                proposed_tool=self._recommendations.proposed_tool_for(record),
                status=record.status,
                governance_status=record.governance_status,
                confidence=record.confidence,
                rank=index,
                rank_reason=self._rank_reason(record),
            )
            for index, record in enumerate(ranked_records, start=1)
        ]

        if not ranked_recommendations:
            return RecommendationSelectionPreview(
                session_id=session_id,
                selection_reason="no_active_recommendations",
                ranked_recommendations=[],
            )

        selected = ranked_recommendations[0]
        return RecommendationSelectionPreview(
            session_id=session_id,
            selected_recommendation_id=selected.recommendation_id,
            selected_proposed_tool=selected.proposed_tool,
            selection_reason=(
                "highest_governance_status_then_confidence_then_recency_then_id"
            ),
            ranked_recommendations=ranked_recommendations,
        )

    def _ranking_key(self, record) -> tuple[int, float, float, str]:
        governance_rank = GOVERNANCE_STATUS_RANK.get(
            record.governance_status,
            -1,
        )
        created_at = self._created_at_timestamp(record.created_at)
        return (
            -governance_rank,
            -record.confidence,
            -created_at,
            record.id,
        )

    def _created_at_timestamp(self, created_at: datetime | str) -> float:
        parsed = (
            created_at
            if isinstance(created_at, datetime)
            else datetime.fromisoformat(created_at)
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).timestamp()

    def _rank_reason(self, record) -> str:
        governance_rank = GOVERNANCE_STATUS_RANK.get(
            record.governance_status,
            -1,
        )
        return (
            f"governance_rank={governance_rank};"
            f"confidence={record.confidence};"
            f"created_at={record.created_at};"
            f"recommendation_id={record.id}"
        )


recommendation_selection_service = RecommendationSelectionService()
