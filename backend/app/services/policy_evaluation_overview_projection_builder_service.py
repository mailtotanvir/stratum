from datetime import UTC, datetime
from typing import Callable

from sqlalchemy import select

from app.db.schema import EvaluationRecord, EvaluationResultRecord
from app.models.policy_evaluation_overview_projection import (
    PolicyEvaluationOverviewProjection,
    PolicyEvaluationPolicySummary,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.policy_service import PolicyService, policy_service


POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE = "policy_evaluation_overview"
POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION = 1
POLICY_EVALUATION_OVERVIEW_SOURCE = (
    "policy_evaluation_overview_projection_builder"
)
POLICY_EVALUATION_OVERVIEW_AUTHORITATIVE_SOURCE = (
    "policies/policy_decisions/policy_violations/evaluations"
)


class PolicyEvaluationOverviewProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None], PolicyEvaluationOverviewProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
        schema_version=POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION,
        builder_name="PolicyEvaluationOverviewProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
            reconstruction_source="policy_evaluation_state",
            authoritative_source=(
                POLICY_EVALUATION_OVERVIEW_AUTHORITATIVE_SOURCE
            ),
        ),
    )
    projection_type = POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE

    def __init__(
        self,
        policies: PolicyService | None = None,
        evaluations: EvaluationService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policies = policies or policy_service
        self._evaluations = evaluations or evaluation_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None],
    ) -> PolicyEvaluationOverviewProjection:
        del source
        generated_at = self._clock()
        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=generated_at,
            source=POLICY_EVALUATION_OVERVIEW_SOURCE,
        )
        policies = self._policies.list_policies()
        persisted_evaluation_ids = self._persisted_evaluation_ids()
        result_evaluation_ids = self._result_evaluation_ids()

        linked_policy_decision_count = 0
        linked_policy_violation_count = 0
        linked_evaluation_ids: set[str] = set()
        policy_summaries: list[PolicyEvaluationPolicySummary] = []
        latest_policy_evidence_at: str | None = None
        policies_with_evidence_count = 0

        for policy in policies:
            decisions = self._policies.list_policy_decisions(policy.id)
            violations = self._policies.list_policy_violations(policy.id)
            linked_decisions = [
                record
                for record in decisions
                if record.evaluation_id is not None
                or record.evaluation_result_id is not None
            ]
            linked_violations = [
                record
                for record in violations
                if record.evaluation_id is not None
                or record.evaluation_result_id is not None
            ]
            policy_linked_evaluation_ids: set[str] = set()

            for record in [*linked_decisions, *linked_violations]:
                policy_linked_evaluation_ids.update(
                    self._valid_linked_evaluation_ids(
                        evaluation_id=record.evaluation_id,
                        evaluation_result_id=record.evaluation_result_id,
                        persisted_evaluation_ids=persisted_evaluation_ids,
                        result_evaluation_ids=result_evaluation_ids,
                    )
                )

            linked_evaluation_ids.update(policy_linked_evaluation_ids)
            linked_policy_decision_count += len(linked_decisions)
            linked_policy_violation_count += len(linked_violations)
            policy_latest_evidence_at = max(
                (
                    record.created_at.isoformat()
                    for record in [*linked_decisions, *linked_violations]
                ),
                default=None,
            )
            if policy_latest_evidence_at is not None:
                policies_with_evidence_count += 1
                if (
                    latest_policy_evidence_at is None
                    or policy_latest_evidence_at > latest_policy_evidence_at
                ):
                    latest_policy_evidence_at = policy_latest_evidence_at

            policy_summaries.append(
                PolicyEvaluationPolicySummary(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    policy_status=policy.status,
                    linked_decision_count=len(linked_decisions),
                    linked_violation_count=len(linked_violations),
                    linked_evaluation_count=len(policy_linked_evaluation_ids),
                    latest_evidence_at=policy_latest_evidence_at,
                )
            )

        return PolicyEvaluationOverviewProjection(
            metadata=metadata,
            policy_count=len(policies),
            evaluation_count=len(persisted_evaluation_ids),
            linked_policy_decision_count=linked_policy_decision_count,
            linked_policy_violation_count=linked_policy_violation_count,
            linked_evaluation_count=len(linked_evaluation_ids),
            unlinked_evaluation_count=(
                len(persisted_evaluation_ids) - len(linked_evaluation_ids)
            ),
            policies_with_evidence_count=policies_with_evidence_count,
            policies_without_evidence_count=(
                len(policies) - policies_with_evidence_count
            ),
            latest_policy_evidence_at=latest_policy_evidence_at,
            generated_at=generated_at,
            policy_summaries=policy_summaries,
        )

    def _persisted_evaluation_ids(self) -> set[str]:
        with self._evaluations.session_factory() as session:
            return set(session.scalars(select(EvaluationRecord.id)).all())

    def _result_evaluation_ids(self) -> dict[str, str]:
        with self._evaluations.session_factory() as session:
            rows = session.execute(
                select(EvaluationResultRecord.id, EvaluationResultRecord.evaluation_id)
            ).all()
        return {result_id: evaluation_id for result_id, evaluation_id in rows}

    @staticmethod
    def _valid_linked_evaluation_ids(
        evaluation_id: str | None,
        evaluation_result_id: str | None,
        persisted_evaluation_ids: set[str],
        result_evaluation_ids: dict[str, str],
    ) -> set[str]:
        linked_ids: set[str] = set()
        if evaluation_id in persisted_evaluation_ids:
            linked_ids.add(evaluation_id)
        if evaluation_result_id in result_evaluation_ids:
            linked_ids.add(result_evaluation_ids[evaluation_result_id])
        return linked_ids


policy_evaluation_overview_projection_builder_service = (
    PolicyEvaluationOverviewProjectionBuilderService()
)
