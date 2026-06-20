from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.query_catalog import QueryCatalogEntry
from app.models.query_executor import (
    QueryExecutionRequest,
    QueryExecutionResult,
)
from app.services.decision_effectiveness_projection_builder_service import (
    DecisionEffectivenessProjectionBuilderService,
    decision_effectiveness_projection_builder_service,
)
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    EvaluationOutcomeRollupProjectionBuilderService,
    evaluation_outcome_rollup_projection_builder_service,
)
from app.services.evaluation_summary_projection_builder_service import (
    EvaluationSummaryProjectionBuilderService,
    evaluation_summary_projection_builder_service,
)
from app.services.evaluation_trend_projection_v2_builder_service import (
    EvaluationTrendProjectionBuilderService,
    evaluation_trend_projection_builder_service,
)
from app.services.governance_health_rollup_projection_builder_service import (
    GovernanceHealthRollupProjectionBuilderService,
    governance_health_rollup_projection_builder_service,
)
from app.services.policy_evaluation_overview_projection_service import (
    PolicyEvaluationOverviewProjectionService,
    policy_evaluation_overview_projection_service,
)
from app.services.policy_evidence_projection_service import (
    PolicyEvidenceProjectionService,
    policy_evidence_projection_service,
)
from app.services.policy_projection_service import (
    PolicyProjectionService,
    policy_projection_service,
)
from app.services.query_catalog_service import (
    QueryCatalogService,
    query_catalog_service,
)
from app.services.recommendation_outcome_projection_builder_service import (
    RecommendationOutcomeProjectionBuilderService,
    recommendation_outcome_projection_builder_service,
)


class QueryExecutionError(ValueError):
    pass


class QueryExecutionNotFoundError(LookupError):
    pass


class QueryExecutorService:
    def __init__(
        self,
        catalog_service: QueryCatalogService | None = None,
        evaluation_service: EvaluationSummaryProjectionBuilderService
        | None = None,
        evaluation_outcome_service: (
            EvaluationOutcomeRollupProjectionBuilderService | None
        ) = None,
        evaluation_trend_service: EvaluationTrendProjectionBuilderService
        | None = None,
        policy_service: PolicyProjectionService | None = None,
        policy_evidence_service: PolicyEvidenceProjectionService | None = None,
        policy_evaluation_overview_service: (
            PolicyEvaluationOverviewProjectionService | None
        ) = None,
        recommendation_outcome_service: (
            RecommendationOutcomeProjectionBuilderService | None
        ) = None,
        decision_effectiveness_service: (
            DecisionEffectivenessProjectionBuilderService | None
        ) = None,
        governance_health_rollup_service: (
            GovernanceHealthRollupProjectionBuilderService | None
        ) = None,
    ) -> None:
        self._catalog_service = catalog_service or query_catalog_service
        self._decision_effectiveness_service = (
            decision_effectiveness_service
            or decision_effectiveness_projection_builder_service
        )
        self._evaluation_service = (
            evaluation_service or evaluation_summary_projection_builder_service
        )
        self._evaluation_outcome_service = (
            evaluation_outcome_service
            or evaluation_outcome_rollup_projection_builder_service
        )
        self._evaluation_trend_service = (
            evaluation_trend_service
            or evaluation_trend_projection_builder_service
        )
        self._governance_health_rollup_service = (
            governance_health_rollup_service
            or governance_health_rollup_projection_builder_service
        )
        self._policy_service = policy_service or policy_projection_service
        self._policy_evidence_service = (
            policy_evidence_service or policy_evidence_projection_service
        )
        self._policy_evaluation_overview_service = (
            policy_evaluation_overview_service
            or policy_evaluation_overview_projection_service
        )
        self._recommendation_outcome_service = (
            recommendation_outcome_service
            or recommendation_outcome_projection_builder_service
        )

    def execute(
        self,
        request: QueryExecutionRequest,
    ) -> QueryExecutionResult:
        entry = self._resolve_catalog_entry(request.query_id)
        dispatch = self._dispatch_table().get(entry.projection_type)
        if dispatch is None:
            raise QueryExecutionError(
                "Query execution is not supported for query_id: "
                f"{request.query_id}"
            )

        result = dispatch(request.filters)
        return QueryExecutionResult(
            query_id=entry.query_id,
            projection_type=entry.projection_type,
            route=entry.route,
            executed_at=datetime.now(UTC),
            result=result,
        )

    def _resolve_catalog_entry(
        self,
        query_id: str,
    ) -> QueryCatalogEntry:
        catalog = self._catalog_service.get_catalog()
        for entry in catalog.entries:
            if query_id in {entry.query_id, entry.projection_type}:
                return entry
        raise QueryExecutionNotFoundError(
            f"Query catalog entry not found: {query_id}"
        )

    def _dispatch_table(
        self,
    ) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "decision_effectiveness": self._execute_decision_effectiveness,
            "evaluation_summary": self._execute_evaluation_summary,
            "evaluation_outcome_rollup": (
                self._execute_evaluation_outcome_rollup
            ),
            "evaluation_trend": self._execute_evaluation_trend,
            "governance_health_rollup": (
                self._execute_governance_health_rollup
            ),
            "policy_summary": self._execute_policy_summary,
            "policy_evidence": self._execute_policy_evidence,
            "policy_evaluation_overview": (
                self._execute_policy_evaluation_overview
            ),
            "recommendation_outcome": self._execute_recommendation_outcome,
        }

    def supported_projection_types(self) -> list[str]:
        return sorted(self._dispatch_table())

    def _execute_decision_effectiveness(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._decision_effectiveness_service.build()

    def _execute_evaluation_summary(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._evaluation_service.build(
            {
                "target_type": filters.get("target_type"),
                "target_id": filters.get("target_id"),
                "evaluation_type": filters.get("evaluation_type"),
                "outcome": filters.get("outcome"),
            }
        )

    def _execute_evaluation_outcome_rollup(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._evaluation_outcome_service.build(
            {
                "target_type": filters.get("target_type"),
                "target_id": filters.get("target_id"),
                "evaluation_type": filters.get("evaluation_type"),
                "outcome": filters.get("outcome"),
            }
        )

    def _execute_evaluation_trend(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._evaluation_trend_service.build(
            {
                "granularity": filters.get("granularity"),
            }
        )

    def _execute_governance_health_rollup(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._governance_health_rollup_service.build()

    def _execute_policy_summary(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._policy_service.list_policy_summaries(
            policy_type=filters.get("policy_type"),
            status=filters.get("status"),
        )

    def _execute_policy_evidence(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._policy_evidence_service.list_policy_evidence(
            policy_id=filters.get("policy_id"),
            evaluation_id=filters.get("evaluation_id"),
            evaluation_result_id=filters.get("evaluation_result_id"),
            target_type=filters.get("target_type"),
            target_id=filters.get("target_id"),
            evidence_type=filters.get("evidence_type"),
        )

    def _execute_policy_evaluation_overview(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return (
            self._policy_evaluation_overview_service
            .get_policy_evaluation_overview()
        )

    def _execute_recommendation_outcome(
        self,
        filters: dict[str, Any],
    ) -> Any:
        return self._recommendation_outcome_service.build()


query_executor_service = QueryExecutorService()
