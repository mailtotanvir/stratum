from collections import defaultdict
from datetime import UTC, datetime
from typing import Callable

from app.models.evaluation_outcome_projection import (
    EvaluationOutcomeDimensionRollup,
    EvaluationOutcomeRollup,
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


EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE = "evaluation_outcome_rollup"
EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION = 1
EVALUATION_OUTCOME_ROLLUP_SOURCE = "evaluation_outcome_projection_builder"


class EvaluationOutcomeProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None], list[EvaluationOutcomeRollup]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
        schema_version=EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION,
        builder_name="EvaluationOutcomeProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
            reconstruction_source="evaluation_state",
            authoritative_source="evaluations/results/target_snapshots",
        ),
    )
    projection_type = EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE

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
    ) -> list[EvaluationOutcomeRollup]:
        built_at = self._clock()
        records = self._evaluations.list_evaluations(
            session_id=source.get("session_id"),
            decision_id=source.get("decision_id"),
            artifact_id=source.get("artifact_id"),
            evaluation_type=source.get("evaluation_type"),
            status=source.get("status"),
        )
        grouped: dict[
            tuple[str, str],
            dict[str, object],
        ] = {}

        for record in records:
            try:
                snapshot = self._evaluations.get_target_snapshot(record.id)
            except EvaluationTargetSnapshotNotFoundError:
                continue

            key = (snapshot.target_type, snapshot.target_id)
            state = grouped.setdefault(
                key,
                {
                    "target_summary": snapshot.target_summary,
                    "evaluations": [],
                    "scores": [],
                    "latest_evaluation_id": None,
                    "latest_evaluation_status": None,
                    "latest_evaluated_at": None,
                    "updated_at": snapshot.created_at.isoformat(),
                    "dimension_scores": defaultdict(list),
                    "dimension_name_by_id": {},
                    "dimension_latest_score": {},
                    "dimension_latest_at": {},
                    "dimension_evaluation_ids": defaultdict(set),
                },
            )
            evaluations = state["evaluations"]
            assert isinstance(evaluations, list)
            evaluations.append(record)

            current_latest = state["latest_evaluated_at"]
            current_latest_str = (
                current_latest if isinstance(current_latest, str) else None
            )
            evaluated_at = record.created_at.isoformat()
            if current_latest_str is None or evaluated_at >= current_latest_str:
                state["latest_evaluation_id"] = record.id
                state["latest_evaluation_status"] = record.status
                state["latest_evaluated_at"] = evaluated_at

            if evaluated_at > str(state["updated_at"]):
                state["updated_at"] = evaluated_at

            results = self._evaluations.get_results(record.id)
            for result in results:
                score = float(result.score)
                scores = state["scores"]
                assert isinstance(scores, list)
                scores.append(score)
                dimension_scores = state["dimension_scores"]
                assert isinstance(dimension_scores, defaultdict)
                dimension_scores[result.dimension_id].append(score)
                state["dimension_name_by_id"][result.dimension_id] = (
                    self._evaluations.get_dimension(result.dimension_id).name
                )
                state["dimension_latest_score"][result.dimension_id] = score
                state["dimension_latest_at"][result.dimension_id] = (
                    result.created_at.isoformat()
                )
                dimension_evaluation_ids = state["dimension_evaluation_ids"]
                assert isinstance(dimension_evaluation_ids, defaultdict)
                dimension_evaluation_ids[result.dimension_id].add(record.id)
                if result.created_at.isoformat() > str(state["updated_at"]):
                    state["updated_at"] = result.created_at.isoformat()

        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=built_at,
            source=EVALUATION_OUTCOME_ROLLUP_SOURCE,
        )
        rollups: list[EvaluationOutcomeRollup] = []
        for (target_type, target_id), state in sorted(grouped.items()):
            scores = state["scores"]
            assert isinstance(scores, list)
            evaluations = state["evaluations"]
            assert isinstance(evaluations, list)
            dimension_scores = state["dimension_scores"]
            assert isinstance(dimension_scores, defaultdict)
            dimension_name_by_id = state["dimension_name_by_id"]
            assert isinstance(dimension_name_by_id, dict)
            dimension_latest_score = state["dimension_latest_score"]
            assert isinstance(dimension_latest_score, dict)
            dimension_latest_at = state["dimension_latest_at"]
            assert isinstance(dimension_latest_at, dict)
            dimension_evaluation_ids = state["dimension_evaluation_ids"]
            assert isinstance(dimension_evaluation_ids, defaultdict)

            dimensions = [
                EvaluationOutcomeDimensionRollup(
                    dimension_id=dimension_id,
                    dimension_name=dimension_name_by_id[dimension_id],
                    evaluation_count=len(dimension_evaluation_ids[dimension_id]),
                    result_count=len(dimension_scores[dimension_id]),
                    average_score=(
                        sum(dimension_scores[dimension_id])
                        / len(dimension_scores[dimension_id])
                    ),
                    latest_score=dimension_latest_score[dimension_id],
                    latest_evaluated_at=dimension_latest_at[dimension_id],
                )
                for dimension_id in sorted(dimension_scores)
            ]
            rollups.append(
                EvaluationOutcomeRollup(
                    metadata=metadata.model_copy(deep=True),
                    target_type=target_type,
                    target_id=target_id,
                    target_summary=str(state["target_summary"]),
                    evaluation_count=len(evaluations),
                    result_count=len(scores),
                    average_score=(sum(scores) / len(scores) if scores else None),
                    min_score=min(scores) if scores else None,
                    max_score=max(scores) if scores else None,
                    latest_evaluation_id=state["latest_evaluation_id"],
                    latest_evaluation_status=state["latest_evaluation_status"],
                    latest_evaluated_at=state["latest_evaluated_at"],
                    dimensions=dimensions,
                    updated_at=str(state["updated_at"]),
                )
            )
        return rollups


evaluation_outcome_projection_builder_service = (
    EvaluationOutcomeProjectionBuilderService()
)
