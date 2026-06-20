from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.decision_record import SelectedEntityType
from app.models.planner import PlannerRecommendationStatus
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.recommendation_outcome_projection import (
    RecommendationOutcomeProjection,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.evaluation_record_service import (
    EvaluationRecordService,
    evaluation_record_service,
)
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)


RECOMMENDATION_OUTCOME_PROJECTION_TYPE = "recommendation_outcome"
RECOMMENDATION_OUTCOME_SCHEMA_VERSION = 1
RECOMMENDATION_OUTCOME_SOURCE = "recommendation_outcome_projection_builder"

SUPPORTED_OUTCOMES = (
    "success",
    "failure",
    "accepted",
    "rejected",
    "reverted",
    "inconclusive",
)


class RecommendationOutcomeProjectionBuilderService(
    BaseProjectionBuilder[Any, list[RecommendationOutcomeProjection]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
        schema_version=RECOMMENDATION_OUTCOME_SCHEMA_VERSION,
        builder_name="RecommendationOutcomeProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
            reconstruction_source=(
                "planner_recommendations,"
                "recommendation_selection_records,"
                "evaluation_records"
            ),
            authoritative_source=(
                "planner_recommendations,"
                "decision_records,"
                "runtime_evaluation_records"
            ),
        ),
    )
    projection_type = RECOMMENDATION_OUTCOME_PROJECTION_TYPE

    def __init__(
        self,
        recommendations: PlannerRecommendationService | None = None,
        decisions: DecisionRecordService | None = None,
        evaluations: EvaluationRecordService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._recommendations = recommendations or planner_recommendation_service
        self._decisions = decisions or decision_record_service
        self._evaluations = evaluations or evaluation_record_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> list[RecommendationOutcomeProjection]:
        recommendations = self._recommendations.list_recommendations()
        recommendation_ids = {record.id for record in recommendations}
        selected_counts = self._selected_counts(
            recommendations,
            recommendation_ids,
        )
        evaluations_by_recommendation = self._evaluations_by_recommendation(
            recommendation_ids
        )
        generated_at = self._clock()

        projections = [
            self._build_projection(
                record,
                selected_counts[record.id],
                evaluations_by_recommendation[record.id],
                generated_at,
            )
            for record in recommendations
        ]
        return sorted(
            projections,
            key=lambda projection: (
                -projection.selected_count,
                -projection.success_rate,
                projection.recommendation_category,
                projection.recommendation_type,
                projection.recommendation_id,
            ),
        )

    def _selected_counts(
        self,
        recommendations: list[Any],
        recommendation_ids: set[str],
    ) -> Counter[str]:
        counts: Counter[str] = Counter()
        for decision in self._decisions.list_decision_records():
            if (
                decision.selected_entity_type
                == SelectedEntityType.PLANNER_RECOMMENDATION.value
                and decision.selected_entity_id in recommendation_ids
            ):
                counts[decision.selected_entity_id] += 1

        for recommendation in recommendations:
            if (
                recommendation.id in recommendation_ids
                and counts[recommendation.id] == 0
                and recommendation.status
                == PlannerRecommendationStatus.PROMOTED.value
            ):
                counts[recommendation.id] = 1
        return counts

    def _evaluations_by_recommendation(
        self,
        recommendation_ids: set[str],
    ) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = defaultdict(list)
        for evaluation in self._evaluations.list_records(
            target_type="recommendation"
        ):
            if evaluation.target_id in recommendation_ids:
                grouped[evaluation.target_id].append(evaluation)
        return grouped

    def _build_projection(
        self,
        recommendation,
        selected_count: int,
        evaluations: list[Any],
        generated_at: datetime,
    ) -> RecommendationOutcomeProjection:
        outcome_counts = Counter(
            str(evaluation.outcome)
            for evaluation in evaluations
            if str(evaluation.outcome) in SUPPORTED_OUTCOMES
        )
        scores = [
            evaluation.score
            for evaluation in evaluations
            if evaluation.score is not None
        ]
        recommendation_type, recommendation_category = (
            self._recommendation_kind(recommendation)
        )
        evaluation_count = len(evaluations)

        return RecommendationOutcomeProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=RECOMMENDATION_OUTCOME_SOURCE,
            ),
            recommendation_id=recommendation.id,
            recommendation_type=recommendation_type,
            recommendation_category=recommendation_category,
            selected_count=selected_count,
            not_selected_count=0 if selected_count else 1,
            evaluation_count=evaluation_count,
            success_count=outcome_counts["success"],
            failure_count=outcome_counts["failure"],
            accepted_count=outcome_counts["accepted"],
            rejected_count=outcome_counts["rejected"],
            reverted_count=outcome_counts["reverted"],
            inconclusive_count=outcome_counts["inconclusive"],
            success_rate=_rate(outcome_counts["success"], evaluation_count),
            average_score=(
                sum(scores) / len(scores)
                if scores
                else None
            ),
            generated_at=generated_at,
        )

    def _recommendation_kind(self, recommendation) -> tuple[str, str]:
        proposed_tool = self._recommendations.proposed_tool_for(recommendation)
        if not proposed_tool:
            return "no_tool", "uncategorized"

        tool_name = _string_or_none(proposed_tool.get("name"))
        tool_id = _string_or_none(proposed_tool.get("id"))
        recommendation_type = tool_name or tool_id or "tool"
        recommendation_category = (
            recommendation_type.split(".", 1)[0]
            if "." in recommendation_type
            else "tool"
        )
        return recommendation_type, recommendation_category


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


recommendation_outcome_projection_builder_service = (
    RecommendationOutcomeProjectionBuilderService()
)
