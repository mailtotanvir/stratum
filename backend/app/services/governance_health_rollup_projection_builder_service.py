from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.governance_health_rollup_projection import (
    GovernanceHealthRollupProjection,
    GovernanceHealthStatus,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.decision_effectiveness_projection_builder_service import (
    DecisionEffectivenessProjectionBuilderService,
    decision_effectiveness_projection_builder_service,
)
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    SUPPORTED_OUTCOMES,
)
from app.services.evaluation_record_service import (
    EvaluationRecordService,
    evaluation_record_service,
)
from app.services.policy_evaluation_overview_projection_builder_service import (
    PolicyEvaluationOverviewProjectionBuilderService,
    policy_evaluation_overview_projection_builder_service,
)
from app.services.recommendation_outcome_projection_builder_service import (
    RecommendationOutcomeProjectionBuilderService,
    recommendation_outcome_projection_builder_service,
)


GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE = "governance_health_rollup"
GOVERNANCE_HEALTH_ROLLUP_SCHEMA_VERSION = 1
GOVERNANCE_HEALTH_ROLLUP_SOURCE = (
    "governance_health_rollup_projection_builder"
)


class GovernanceHealthRollupProjectionBuilderService(
    BaseProjectionBuilder[Any, GovernanceHealthRollupProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
        schema_version=GOVERNANCE_HEALTH_ROLLUP_SCHEMA_VERSION,
        builder_name="GovernanceHealthRollupProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
            reconstruction_source=(
                "evaluation_records,"
                "recommendation_outcome_projection,"
                "decision_effectiveness_projection,"
                "policy_evaluation_overview_projection"
            ),
            authoritative_source=(
                "runtime_evaluation_records,"
                "planner_recommendations,"
                "decision_records,"
                "policies"
            ),
        ),
    )
    projection_type = GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE

    def __init__(
        self,
        evaluations: EvaluationRecordService | None = None,
        recommendations: RecommendationOutcomeProjectionBuilderService | None = None,
        decisions: DecisionEffectivenessProjectionBuilderService | None = None,
        policies: PolicyEvaluationOverviewProjectionBuilderService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_record_service
        self._recommendations = (
            recommendations or recommendation_outcome_projection_builder_service
        )
        self._decisions = (
            decisions or decision_effectiveness_projection_builder_service
        )
        self._policies = policies or policy_evaluation_overview_projection_builder_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> GovernanceHealthRollupProjection:
        del source
        records = self._evaluations.list_records()
        counts = Counter(
            str(record.outcome)
            for record in records
            if str(record.outcome) in SUPPORTED_OUTCOMES
        )
        scores = [
            float(record.score)
            for record in records
            if record.score is not None
        ]
        total = len(records)

        overall_success_rate = _rate(counts["success"], total)
        overall_failure_rate = _rate(counts["failure"], total)
        overall_rejection_rate = _rate(counts["rejected"], total)
        overall_reversion_rate = _rate(counts["reverted"], total)
        health_status, health_reasons = _health_status(
            total,
            overall_success_rate,
            overall_reversion_rate,
        )
        generated_at = self._clock()

        recommendation_projections = self._recommendations.build()
        decision_projections = self._decisions.build()
        policy_projections = self._policies.build()

        return GovernanceHealthRollupProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=GOVERNANCE_HEALTH_ROLLUP_SOURCE,
            ),
            total_evaluations=total,
            overall_success_rate=overall_success_rate,
            overall_failure_rate=overall_failure_rate,
            overall_rejection_rate=overall_rejection_rate,
            overall_reversion_rate=overall_reversion_rate,
            average_evaluation_score=(
                sum(scores) / len(scores)
                if scores
                else None
            ),
            recommendation_success_rate=_aggregate_success_rate(
                [
                    (projection.success_count, projection.evaluation_count)
                    for projection in recommendation_projections
                ]
            ),
            decision_success_rate=_aggregate_success_rate(
                [
                    (projection.success_count, projection.evaluation_count)
                    for projection in decision_projections
                ]
            ),
            decision_evaluation_coverage_rate=_rate(
                sum(
                    1
                    for projection in decision_projections
                    if projection.has_evaluation_coverage
                ),
                len(decision_projections),
            ),
            policy_success_rate=_aggregate_success_rate(
                [
                    (projection.success_count, projection.total_evaluations)
                    for projection in policy_projections
                ]
            ),
            health_status=health_status,
            health_reasons=health_reasons,
            generated_at=generated_at,
        )


def _aggregate_success_rate(values: list[tuple[int, int]]) -> float:
    successes = sum(success_count for success_count, _ in values)
    evaluations = sum(evaluation_count for _, evaluation_count in values)
    return _rate(successes, evaluations)


def _health_status(
    total_evaluations: int,
    success_rate: float,
    reversion_rate: float,
) -> tuple[GovernanceHealthStatus, list[str]]:
    if total_evaluations == 0:
        return "unknown", ["no_evaluation_data"]
    if success_rate >= 0.8 and reversion_rate <= 0.05:
        return "healthy", [
            "overall_success_rate_at_least_0.8",
            "overall_reversion_rate_at_most_0.05",
        ]
    if success_rate >= 0.6:
        return "watch", [
            "overall_success_rate_at_least_0.6",
            "healthy_threshold_not_met",
        ]
    return "degraded", ["overall_success_rate_below_0.6"]


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


governance_health_rollup_projection_builder_service = (
    GovernanceHealthRollupProjectionBuilderService()
)
