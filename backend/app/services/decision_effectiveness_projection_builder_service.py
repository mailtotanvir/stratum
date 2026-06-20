from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.decision_effectiveness_projection import (
    DecisionEffectivenessProjection,
)
from app.models.evaluation_record import EvaluationRecord
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    SUPPORTED_OUTCOMES,
)
from app.services.evaluation_record_service import (
    EvaluationRecordService,
    evaluation_record_service,
)


DECISION_EFFECTIVENESS_PROJECTION_TYPE = "decision_effectiveness"
DECISION_EFFECTIVENESS_SCHEMA_VERSION = 1
DECISION_EFFECTIVENESS_SOURCE = "decision_effectiveness_projection_builder"


class DecisionEffectivenessProjectionBuilderService(
    BaseProjectionBuilder[Any, list[DecisionEffectivenessProjection]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=DECISION_EFFECTIVENESS_PROJECTION_TYPE,
        schema_version=DECISION_EFFECTIVENESS_SCHEMA_VERSION,
        builder_name="DecisionEffectivenessProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=DECISION_EFFECTIVENESS_PROJECTION_TYPE,
            reconstruction_source="decision_records,evaluation_records",
            authoritative_source="decision_records,runtime_evaluation_records",
        ),
    )
    projection_type = DECISION_EFFECTIVENESS_PROJECTION_TYPE

    def __init__(
        self,
        decisions: DecisionRecordService | None = None,
        evaluations: EvaluationRecordService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._decisions = decisions or decision_record_service
        self._evaluations = evaluations or evaluation_record_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> list[DecisionEffectivenessProjection]:
        del source
        decisions = self._decisions.list_decision_records()
        decision_ids = {decision.decision_id for decision in decisions}
        evaluations_by_decision = self._evaluations_by_decision(decision_ids)
        generated_at = self._clock()
        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=generated_at,
            source=DECISION_EFFECTIVENESS_SOURCE,
        )

        projections = [
            _build_decision_projection(
                metadata=metadata,
                decision=decision,
                records=evaluations_by_decision[decision.decision_id],
                generated_at=generated_at,
            )
            for decision in decisions
        ]
        return sorted(
            projections,
            key=lambda projection: (
                -projection.evaluation_count,
                -projection.success_rate,
                projection.decision_type,
                projection.decision_id,
            ),
        )

    def _evaluations_by_decision(
        self,
        decision_ids: set[str],
    ) -> dict[str, list[EvaluationRecord]]:
        grouped: dict[str, list[EvaluationRecord]] = defaultdict(list)
        for evaluation in self._evaluations.list_records(
            target_type="decision"
        ):
            if evaluation.target_id in decision_ids:
                grouped[evaluation.target_id].append(evaluation)
        return grouped


def _build_decision_projection(
    *,
    metadata: ProjectionMetadata,
    decision: Any,
    records: list[EvaluationRecord],
    generated_at: datetime,
) -> DecisionEffectivenessProjection:
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
    evaluation_count = len(records)

    return DecisionEffectivenessProjection(
        metadata=metadata.model_copy(deep=True),
        decision_id=decision.decision_id,
        decision_type=str(decision.decision_type),
        session_id=decision.session_id,
        task_id=decision.task_id,
        evaluation_count=evaluation_count,
        success_count=counts["success"],
        failure_count=counts["failure"],
        accepted_count=counts["accepted"],
        rejected_count=counts["rejected"],
        reverted_count=counts["reverted"],
        inconclusive_count=counts["inconclusive"],
        success_rate=_rate(counts["success"], evaluation_count),
        failure_rate=_rate(counts["failure"], evaluation_count),
        average_score=(sum(scores) / len(scores) if scores else None),
        has_evaluation_coverage=evaluation_count > 0,
        generated_at=generated_at,
    )


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


decision_effectiveness_projection_builder_service = (
    DecisionEffectivenessProjectionBuilderService()
)
