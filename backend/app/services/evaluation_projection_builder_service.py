from collections import defaultdict
from datetime import UTC, datetime
from typing import Callable

from app.models.evaluation_projection import (
    EvaluationDimensionSummary,
    EvaluationSummaryProjection,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_service import (
    EvaluationService,
    EvaluationTargetSnapshotNotFoundError,
    evaluation_service,
)


EVALUATION_SUMMARY_PROJECTION_TYPE = "evaluation_summary"
EVALUATION_SUMMARY_SCHEMA_VERSION = 1
EVALUATION_SUMMARY_SOURCE = "evaluation_projection_builder"


class EvaluationProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None], list[EvaluationSummaryProjection]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_SUMMARY_PROJECTION_TYPE,
        schema_version=EVALUATION_SUMMARY_SCHEMA_VERSION,
        builder_name="EvaluationProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_SUMMARY_PROJECTION_TYPE,
            reconstruction_source="evaluation_state",
            authoritative_source="evaluations/results",
        ),
    )
    projection_type = EVALUATION_SUMMARY_PROJECTION_TYPE

    def __init__(
        self,
        evaluations: EvaluationService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None],
    ) -> list[EvaluationSummaryProjection]:
        built_at = self._clock()
        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=built_at,
            source=EVALUATION_SUMMARY_SOURCE,
        )
        records = self._evaluations.list_evaluations(
            session_id=source.get("session_id"),
            decision_id=source.get("decision_id"),
            artifact_id=source.get("artifact_id"),
            evaluation_type=source.get("evaluation_type"),
            status=source.get("status"),
        )

        projections: list[EvaluationSummaryProjection] = []
        for record in records:
            results = self._evaluations.get_results(record.id)
            try:
                target_snapshot = self._evaluations.get_target_snapshot(record.id)
            except EvaluationTargetSnapshotNotFoundError:
                target_snapshot = None
            dimensions_by_id: dict[str, list[float]] = defaultdict(list)
            latest_score_by_dimension: dict[str, float] = {}
            dimension_name_by_id: dict[str, str] = {}
            latest_updated_at = record.created_at
            scores: list[float] = []

            for result in results:
                scores.append(float(result.score))
                dimensions_by_id[result.dimension_id].append(float(result.score))
                latest_score_by_dimension[result.dimension_id] = float(result.score)
                dimension_name_by_id[result.dimension_id] = (
                    self._evaluations.get_dimension(result.dimension_id).name
                )
                if result.created_at > latest_updated_at:
                    latest_updated_at = result.created_at

            dimension_summaries = [
                EvaluationDimensionSummary(
                    dimension_id=dimension_id,
                    dimension_name=dimension_name_by_id[dimension_id],
                    result_count=len(dimension_scores),
                    average_score=sum(dimension_scores) / len(dimension_scores),
                    latest_score=latest_score_by_dimension[dimension_id],
                )
                for dimension_id, dimension_scores in sorted(
                    dimensions_by_id.items()
                )
            ]

            projections.append(
                EvaluationSummaryProjection(
                    metadata=metadata.model_copy(deep=True),
                    evaluation_id=record.id,
                    session_id=record.session_id,
                    decision_id=record.decision_id,
                    artifact_id=record.artifact_id,
                    target_type=(
                        target_snapshot.target_type
                        if target_snapshot is not None
                        else None
                    ),
                    target_id=(
                        target_snapshot.target_id
                        if target_snapshot is not None
                        else None
                    ),
                    target_summary=(
                        target_snapshot.target_summary
                        if target_snapshot is not None
                        else None
                    ),
                    evaluation_type=record.evaluation_type,
                    status=record.status,
                    result_count=len(results),
                    average_score=(
                        sum(scores) / len(scores) if scores else None
                    ),
                    min_score=min(scores) if scores else None,
                    max_score=max(scores) if scores else None,
                    dimensions=dimension_summaries,
                    created_at=record.created_at.isoformat(),
                    updated_at=latest_updated_at.isoformat(),
                )
            )
        return projections


evaluation_projection_builder_service = EvaluationProjectionBuilderService()
