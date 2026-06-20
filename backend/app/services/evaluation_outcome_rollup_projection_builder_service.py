from collections import Counter
from datetime import UTC, datetime
from typing import Callable

from app.models.evaluation_outcome_rollup_projection import (
    EvaluationOutcomeRollupProjection,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_record_service import (
    EvaluationRecordService,
    evaluation_record_service,
)


EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE = "evaluation_outcome_rollup"
EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION = 1
EVALUATION_OUTCOME_ROLLUP_SOURCE = (
    "evaluation_outcome_rollup_projection_builder"
)

SUPPORTED_OUTCOMES = (
    "success",
    "failure",
    "accepted",
    "rejected",
    "reverted",
    "inconclusive",
)


class EvaluationOutcomeRollupProjectionBuilderService(
    BaseProjectionBuilder[
        dict[str, str | None] | None,
        EvaluationOutcomeRollupProjection,
    ]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
        schema_version=EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION,
        builder_name="EvaluationOutcomeRollupProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
            reconstruction_source="evaluation_records",
            authoritative_source="runtime_evaluation_records",
        ),
    )
    projection_type = EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE

    def __init__(
        self,
        evaluations: EvaluationRecordService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_record_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None] | None = None,
    ) -> EvaluationOutcomeRollupProjection:
        filters = source or {}
        records = self._evaluations.list_records(
            target_type=filters.get("target_type"),  # type: ignore[arg-type]
            target_id=filters.get("target_id"),
            evaluation_type=filters.get("evaluation_type"),
            outcome=filters.get("outcome"),  # type: ignore[arg-type]
        )
        generated_at = self._clock()
        counts = Counter(
            str(record.outcome)
            for record in records
            if str(record.outcome) in SUPPORTED_OUTCOMES
        )
        total = len(records)

        return EvaluationOutcomeRollupProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_OUTCOME_ROLLUP_SOURCE,
            ),
            total_evaluations=total,
            success_count=counts["success"],
            failure_count=counts["failure"],
            accepted_count=counts["accepted"],
            rejected_count=counts["rejected"],
            reverted_count=counts["reverted"],
            inconclusive_count=counts["inconclusive"],
            success_rate=_rate(counts["success"], total),
            failure_rate=_rate(counts["failure"], total),
            acceptance_rate=_rate(counts["accepted"], total),
            rejection_rate=_rate(counts["rejected"], total),
            reversion_rate=_rate(counts["reverted"], total),
            inconclusive_rate=_rate(counts["inconclusive"], total),
            generated_at=generated_at,
        )


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


evaluation_outcome_rollup_projection_builder_service = (
    EvaluationOutcomeRollupProjectionBuilderService()
)
