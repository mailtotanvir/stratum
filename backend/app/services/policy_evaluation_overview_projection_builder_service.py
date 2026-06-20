from collections import Counter
from datetime import UTC, datetime
from typing import Callable

from app.models.evaluation_record import EvaluationRecord
from app.models.policy_evaluation_overview_projection import (
    PolicyEvaluationOverviewProjection,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    SUPPORTED_OUTCOMES,
)
from app.services.evaluation_record_service import (
    EvaluationRecordService,
    evaluation_record_service,
)
from app.services.policy_service import PolicyService, policy_service


POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE = "policy_evaluation_overview"
POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION = 1
POLICY_EVALUATION_OVERVIEW_SOURCE = (
    "policy_evaluation_overview_projection_builder"
)
POLICY_EVALUATION_OVERVIEW_AUTHORITATIVE_SOURCE = (
    "policies/policy_decisions/policy_violations/runtime_evaluation_records"
)


class PolicyEvaluationOverviewProjectionBuilderService(
    BaseProjectionBuilder[
        dict[str, str | None] | None,
        list[PolicyEvaluationOverviewProjection],
    ]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
        schema_version=POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION,
        builder_name="PolicyEvaluationOverviewProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
            reconstruction_source="policy_evaluation_records",
            authoritative_source=(
                POLICY_EVALUATION_OVERVIEW_AUTHORITATIVE_SOURCE
            ),
        ),
    )
    projection_type = POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE

    def __init__(
        self,
        policies: PolicyService | None = None,
        evaluations: EvaluationRecordService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policies = policies or policy_service
        self._evaluations = evaluations or evaluation_record_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None] | None = None,
    ) -> list[PolicyEvaluationOverviewProjection]:
        del source
        generated_at = self._clock()
        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=generated_at,
            source=POLICY_EVALUATION_OVERVIEW_SOURCE,
        )
        evaluations_by_id = {
            record.evaluation_id: record
            for record in self._evaluations.list_records()
        }

        projections: list[PolicyEvaluationOverviewProjection] = []
        for policy in self._policies.list_policies():
            linked_evaluation_ids = self._linked_evaluation_ids(policy.id)
            records = [
                evaluations_by_id[evaluation_id]
                for evaluation_id in sorted(linked_evaluation_ids)
                if evaluation_id in evaluations_by_id
            ]
            projections.append(
                _build_policy_projection(
                    metadata=metadata,
                    policy_id=policy.id,
                    policy_name=policy.name,
                    records=records,
                    generated_at=generated_at,
                )
            )

        return sorted(
            projections,
            key=lambda projection: (
                -projection.total_evaluations,
                projection.policy_name,
                projection.policy_id,
            ),
        )

    def _linked_evaluation_ids(self, policy_id: str) -> set[str]:
        linked_ids: set[str] = set()
        for decision in self._policies.list_policy_decisions(policy_id):
            if decision.evaluation_id is not None:
                linked_ids.add(decision.evaluation_id)
        for violation in self._policies.list_policy_violations(policy_id):
            if violation.evaluation_id is not None:
                linked_ids.add(violation.evaluation_id)
        return linked_ids


def _build_policy_projection(
    *,
    metadata: ProjectionMetadata,
    policy_id: str,
    policy_name: str,
    records: list[EvaluationRecord],
    generated_at: datetime,
) -> PolicyEvaluationOverviewProjection:
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
    return PolicyEvaluationOverviewProjection(
        metadata=metadata.model_copy(deep=True),
        policy_id=policy_id,
        policy_name=policy_name,
        total_evaluations=len(records),
        success_count=counts["success"],
        failure_count=counts["failure"],
        accepted_count=counts["accepted"],
        rejected_count=counts["rejected"],
        reverted_count=counts["reverted"],
        inconclusive_count=counts["inconclusive"],
        average_score=(sum(scores) / len(scores) if scores else None),
        generated_at=generated_at,
    )


policy_evaluation_overview_projection_builder_service = (
    PolicyEvaluationOverviewProjectionBuilderService()
)
