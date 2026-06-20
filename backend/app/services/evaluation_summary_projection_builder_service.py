from collections import defaultdict
from datetime import UTC, datetime
from typing import Callable

from app.models.evaluation_summary_projection import EvaluationSummaryProjection
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


EVALUATION_SUMMARY_PROJECTION_TYPE = "evaluation_summary"
EVALUATION_SUMMARY_SCHEMA_VERSION = 1
EVALUATION_SUMMARY_SOURCE = "evaluation_summary_projection_builder"


class EvaluationSummaryProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None] | None, EvaluationSummaryProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_SUMMARY_PROJECTION_TYPE,
        schema_version=EVALUATION_SUMMARY_SCHEMA_VERSION,
        builder_name="EvaluationSummaryProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_SUMMARY_PROJECTION_TYPE,
            reconstruction_source="evaluation_records",
            authoritative_source="runtime_evaluation_records",
        ),
    )
    projection_type = EVALUATION_SUMMARY_PROJECTION_TYPE

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
    ) -> EvaluationSummaryProjection:
        filters = source or {}
        records = self._evaluations.list_records(
            target_type=filters.get("target_type"),  # type: ignore[arg-type]
            target_id=filters.get("target_id"),
            evaluation_type=filters.get("evaluation_type"),
            outcome=filters.get("outcome"),  # type: ignore[arg-type]
        )
        generated_at = self._clock()
        scores_by_type: dict[str, list[float]] = defaultdict(list)
        scores_by_target_type: dict[str, list[float]] = defaultdict(list)
        evaluations_by_type: dict[str, int] = defaultdict(int)
        evaluations_by_outcome: dict[str, int] = defaultdict(int)
        evaluations_by_target_type: dict[str, int] = defaultdict(int)

        for record in records:
            evaluations_by_type[record.evaluation_type] += 1
            evaluations_by_outcome[record.outcome] += 1
            evaluations_by_target_type[record.target_type] += 1
            if record.score is None:
                continue
            scores_by_type[record.evaluation_type].append(float(record.score))
            scores_by_target_type[record.target_type].append(
                float(record.score)
            )

        return EvaluationSummaryProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_SUMMARY_SOURCE,
            ),
            total_evaluations=len(records),
            evaluations_by_type=dict(sorted(evaluations_by_type.items())),
            evaluations_by_outcome=dict(sorted(evaluations_by_outcome.items())),
            evaluations_by_target_type=dict(
                sorted(evaluations_by_target_type.items())
            ),
            average_score_by_evaluation_type=_averages(scores_by_type),
            average_score_by_target_type=_averages(scores_by_target_type),
            generated_at=generated_at,
        )


def _averages(scores_by_key: dict[str, list[float]]) -> dict[str, float]:
    return {
        key: sum(scores) / len(scores)
        for key, scores in sorted(scores_by_key.items())
        if scores
    }


evaluation_summary_projection_builder_service = (
    EvaluationSummaryProjectionBuilderService()
)
