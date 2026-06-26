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
    EvaluationDiagnosticsProjection,
    EvaluationProjectionDiagnostics,
)
from app.runtime.projection_registry import (
    ProjectionTypeNotFoundError,
    projection_registry as runtime_projection_registry,
)
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.projection_registry_service import (
    ProjectionContractNotFoundError,
    ProjectionRegistryService,
    projection_registry_service,
)


EVALUATION_PROJECTION_PREFIX = "evaluation_"


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

        projections = self._projection_diagnostics()
        healthy_projections = sum(
            1
            for projection in projections
            if projection.health_status == "healthy"
        )
        rebuildable_projections = sum(
            1 for projection in projections if projection.rebuild_supported
        )
        dependency_failures = sum(
            1
            for projection in projections
            if projection.dependency_status != "healthy"
        )
        unhealthy_projections = len(projections) - healthy_projections
        overall_health = (
            "healthy" if unhealthy_projections == 0 else "unhealthy"
        )

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
                projection.projection_name
                for projection in projections
                if projection.registered
            ],
            projections=projections,
            total_projections=len(projections),
            healthy_projections=healthy_projections,
            unhealthy_projections=unhealthy_projections,
            rebuildable_projections=rebuildable_projections,
            dependency_failures=dependency_failures,
            overall_health=overall_health,
            generated_at=datetime.now(UTC),
        )

    def projection(self) -> EvaluationDiagnosticsProjection:
        diagnostics = self.generate()
        return EvaluationDiagnosticsProjection(
            projections=diagnostics.projections,
            total_projections=diagnostics.total_projections,
            healthy_projections=diagnostics.healthy_projections,
            unhealthy_projections=diagnostics.unhealthy_projections,
            rebuildable_projections=diagnostics.rebuildable_projections,
            dependency_failures=diagnostics.dependency_failures,
            overall_health=diagnostics.overall_health,
            generated_at=diagnostics.generated_at,
        )

    def summary(self) -> dict[str, int | str]:
        diagnostics = self.generate()
        return {
            "projection_count": diagnostics.total_projections,
            "healthy_projections": diagnostics.healthy_projections,
            "unhealthy_projections": diagnostics.unhealthy_projections,
            "dependency_failures": diagnostics.dependency_failures,
            "overall_health": diagnostics.overall_health,
        }

    def _projection_diagnostics(self) -> list[EvaluationProjectionDiagnostics]:
        entries = [
            entry
            for entry in self._projection_registry.list_registry().projections
            if entry.category == "evaluations"
            and entry.projection_name.startswith(EVALUATION_PROJECTION_PREFIX)
        ]
        return [
            self._entry_diagnostics(entry.projection_name)
            for entry in sorted(entries, key=lambda entry: entry.projection_name)
        ]

    def _entry_diagnostics(
        self,
        projection_name: str,
    ) -> EvaluationProjectionDiagnostics:
        try:
            detail = self._projection_registry.get(projection_name)
            registered = True
            rebuild_supported = detail.capabilities.reconstructable
            route = detail.route
            dependencies = self._dependencies(projection_name)
            source = self._source(projection_name)
            dependency_count = len(dependencies)
            dependency_status = self._dependency_status(dependencies)
        except ProjectionContractNotFoundError:
            registered = False
            rebuild_supported = False
            route = ""
            source = ""
            dependency_count = 0
            dependency_status = "unhealthy"

        health_status = (
            "healthy"
            if registered and rebuild_supported and dependency_status == "healthy"
            else "unhealthy"
        )
        return EvaluationProjectionDiagnostics(
            projection_name=projection_name,
            projection_type=projection_name,
            registered=registered,
            rebuild_supported=rebuild_supported,
            rebuildable=rebuild_supported,
            persisted=False,
            source=source,
            route=route,
            dependency_count=dependency_count,
            dependency_status=dependency_status,
            record_count=0,
            health_status=health_status,
            reconstruction_status=(
                "supported" if rebuild_supported else "unsupported"
            ),
            replay_verified=False,
        )

    def _source(self, projection_name: str) -> str:
        try:
            return (
                runtime_projection_registry.get_schema(projection_name)
                .reconstruction
                .authoritative_source
            )
        except ProjectionTypeNotFoundError:
            return "projection_registry"

    def _dependencies(self, projection_name: str) -> list[str]:
        try:
            source = (
                runtime_projection_registry.get_schema(projection_name)
                .reconstruction
                .reconstruction_source
            )
        except ProjectionTypeNotFoundError:
            return []
        dependencies = [
            item.strip()
            for item in source.split(",")
            if item.strip().startswith(EVALUATION_PROJECTION_PREFIX)
        ]
        return [
            dependency
            for dependency in dependencies
            if dependency != projection_name
            and self._registered_dependency(dependency)
        ]

    def _dependency_status(self, dependencies: list[str]) -> str:
        for dependency in dependencies:
            try:
                self._projection_registry.get(dependency)
            except ProjectionContractNotFoundError:
                return "unhealthy"
        return "healthy"

    def _registered_dependency(self, dependency: str) -> bool:
        try:
            self._projection_registry.get(dependency)
        except ProjectionContractNotFoundError:
            return False
        return True


evaluation_diagnostics_service = EvaluationDiagnosticsService()
