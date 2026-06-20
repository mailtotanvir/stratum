from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.schema import (
    EvaluationDimensionRecord,
    EvaluationRecord,
    EvaluationResultRecord,
    EvaluationTargetSnapshotRecord,
)
from app.models.evaluation_diagnostics import (
    EvaluationDiagnostics,
    EvaluationProjectionDiagnostics,
)
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.projection_registry_service import (
    ProjectionContractNotFoundError,
    ProjectionRegistryService,
    projection_registry_service,
)


EVALUATION_PROJECTION_SPECS = {
    "evaluation_summary": {
        "source": "runtime_evaluation_records",
        "route": "/runtime/evaluation-summary",
    },
    "evaluation_outcome_rollup": {
        "source": "runtime_evaluation_records",
        "route": "/runtime/evaluation-outcome-rollup",
    },
    "evaluation_trend": {
        "source": "runtime_evaluation_records",
        "route": "/runtime/evaluation-trend",
    },
}


class EvaluationDiagnosticsService:
    def __init__(
        self,
        evaluations: EvaluationService | None = None,
        projection_registry: ProjectionRegistryService | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_service
        self._projection_registry = (
            projection_registry or projection_registry_service
        )

    def generate(self) -> EvaluationDiagnostics:
        with self._evaluations.session_factory() as session:
            evaluation_count = session.scalar(
                select(func.count()).select_from(EvaluationRecord)
            )
            result_count = session.scalar(
                select(func.count()).select_from(EvaluationResultRecord)
            )
            dimension_count = session.scalar(
                select(func.count()).select_from(EvaluationDimensionRecord)
            )
            target_snapshot_count = session.scalar(
                select(func.count()).select_from(EvaluationTargetSnapshotRecord)
            )
            evaluations_without_results_count = session.scalar(
                select(func.count())
                .select_from(EvaluationRecord)
                .outerjoin(
                    EvaluationResultRecord,
                    EvaluationResultRecord.evaluation_id == EvaluationRecord.id,
                )
                .where(EvaluationResultRecord.id.is_(None))
            )
            evaluations_without_target_snapshot_count = session.scalar(
                select(func.count())
                .select_from(EvaluationRecord)
                .outerjoin(
                    EvaluationTargetSnapshotRecord,
                    EvaluationTargetSnapshotRecord.evaluation_id
                    == EvaluationRecord.id,
                )
                .where(EvaluationTargetSnapshotRecord.evaluation_id.is_(None))
            )

        projection_types = sorted(EVALUATION_PROJECTION_SPECS)
        return EvaluationDiagnostics(
            evaluation_count=int(evaluation_count or 0),
            result_count=int(result_count or 0),
            dimension_count=int(dimension_count or 0),
            target_snapshot_count=int(target_snapshot_count or 0),
            evaluations_without_results_count=int(
                evaluations_without_results_count or 0
            ),
            evaluations_without_target_snapshot_count=int(
                evaluations_without_target_snapshot_count or 0
            ),
            registered_projection_types=[
                projection_type
                for projection_type in projection_types
                if self._projection_registered(projection_type)
            ],
            projections=[
                self._projection_diagnostics(projection_type)
                for projection_type in projection_types
            ],
            generated_at=datetime.now(UTC),
        )

    def _projection_registered(self, projection_type: str) -> bool:
        try:
            self._projection_registry.get(projection_type)
        except ProjectionContractNotFoundError:
            return False
        return True

    def _projection_diagnostics(
        self,
        projection_type: str,
    ) -> EvaluationProjectionDiagnostics:
        spec = EVALUATION_PROJECTION_SPECS[projection_type]
        try:
            detail = self._projection_registry.get(projection_type)
            registered = True
            rebuildable = detail.capabilities.replayable
        except ProjectionContractNotFoundError:
            registered = False
            rebuildable = False

        return EvaluationProjectionDiagnostics(
            projection_type=projection_type,
            registered=registered,
            rebuildable=rebuildable,
            persisted=False,
            source=spec["source"],
            route=spec["route"],
        )


evaluation_diagnostics_service = EvaluationDiagnosticsService()
