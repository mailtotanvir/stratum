from datetime import UTC, datetime
from typing import Any, Callable

from app.models.evaluation_coverage import EvaluationCoverageProjection
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_coverage_service import (
    EvaluationCoverageService,
    evaluation_coverage_service,
)


EVALUATION_COVERAGE_PROJECTION_TYPE = "evaluation_coverage"
EVALUATION_COVERAGE_SCHEMA_VERSION = 1
EVALUATION_COVERAGE_SOURCE = "evaluation_coverage_projection_builder"


class EvaluationCoverageProjectionBuilderService(
    BaseProjectionBuilder[Any, EvaluationCoverageProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_COVERAGE_PROJECTION_TYPE,
        schema_version=EVALUATION_COVERAGE_SCHEMA_VERSION,
        builder_name="EvaluationCoverageProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_COVERAGE_PROJECTION_TYPE,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = EVALUATION_COVERAGE_PROJECTION_TYPE

    def __init__(
        self,
        coverage: EvaluationCoverageService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._coverage = coverage or evaluation_coverage_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> EvaluationCoverageProjection:
        del source
        generated_at = self._clock()
        return self._coverage.build_projection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_COVERAGE_SOURCE,
            ),
            generated_at=generated_at,
        )


evaluation_coverage_projection_builder_service = (
    EvaluationCoverageProjectionBuilderService()
)
