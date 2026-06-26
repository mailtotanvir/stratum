from datetime import datetime
from typing import Protocol

from app.models.evaluation_coverage import EvaluationCoverageProjection
from app.models.evaluation_drift import EvaluationDriftProjection
from app.models.evaluation_intelligence_overview import (
    EvaluationIntelligenceOverviewProjection,
)
from app.models.evaluation_lineage import EvaluationLineageProjection
from app.models.evaluation_registry import EvaluationRegistryProjection
from app.models.projection import ProjectionMetadata
from app.services.evaluation_coverage_projection_builder_service import (
    evaluation_coverage_projection_builder_service,
)
from app.services.evaluation_drift_projection_builder_service import (
    evaluation_drift_projection_builder_service,
)
from app.services.evaluation_lineage_projection_builder_service import (
    evaluation_lineage_projection_builder_service,
)
from app.services.evaluation_registry_projection_builder_service import (
    evaluation_registry_projection_builder_service,
)


class EvaluationRegistryProjectionProvider(Protocol):
    def build(self) -> EvaluationRegistryProjection:
        ...


class EvaluationLineageProjectionProvider(Protocol):
    def build(self) -> EvaluationLineageProjection:
        ...


class EvaluationCoverageProjectionProvider(Protocol):
    def build(self) -> EvaluationCoverageProjection:
        ...


class EvaluationDriftProjectionProvider(Protocol):
    def build(self) -> EvaluationDriftProjection:
        ...


class EvaluationIntelligenceOverviewService:
    def __init__(
        self,
        registry: EvaluationRegistryProjectionProvider | None = None,
        lineage: EvaluationLineageProjectionProvider | None = None,
        coverage: EvaluationCoverageProjectionProvider | None = None,
        drift: EvaluationDriftProjectionProvider | None = None,
    ) -> None:
        self._registry = (
            registry or evaluation_registry_projection_builder_service
        )
        self._lineage = lineage or evaluation_lineage_projection_builder_service
        self._coverage = (
            coverage or evaluation_coverage_projection_builder_service
        )
        self._drift = drift or evaluation_drift_projection_builder_service

    def build_projection(
        self,
        *,
        metadata: ProjectionMetadata,
        generated_at: datetime,
    ) -> EvaluationIntelligenceOverviewProjection:
        registry = self._registry.build()
        lineage = self._lineage.build()
        coverage = self._coverage.build()
        drift = self._drift.build()

        regressing_evaluation_ids = {
            record.evaluation_id
            for record in drift.drift_records
            if record.drift_status == "regressed"
        }
        regressing_evaluations = len(regressing_evaluation_ids)
        healthy_evaluations = max(
            registry.total_definitions - regressing_evaluations,
            0,
        )

        return EvaluationIntelligenceOverviewProjection(
            metadata=metadata,
            total_evaluations=registry.total_definitions,
            total_suites=registry.total_suites,
            total_coverage_targets=coverage.total_targets,
            covered_targets=len(coverage.covered_targets),
            uncovered_targets=len(coverage.uncovered_targets),
            coverage_percentage=coverage.coverage_percentage,
            total_lineage_records=lineage.total_lineage_records,
            total_evidence_records=lineage.total_evidence_records,
            total_drift_records=drift.total_drift_records,
            regressed_count=drift.regressed_count,
            improved_count=drift.improved_count,
            unchanged_count=drift.unchanged_count,
            healthy_evaluations=healthy_evaluations,
            regressing_evaluations=regressing_evaluations,
            generated_at=generated_at,
        )


evaluation_intelligence_overview_service = (
    EvaluationIntelligenceOverviewService()
)
