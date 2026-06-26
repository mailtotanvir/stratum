from datetime import UTC, datetime
from typing import Any, Callable

from app.models.evaluation_intelligence_overview import (
    EvaluationIntelligenceOverviewProjection,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_intelligence_overview_service import (
    EvaluationIntelligenceOverviewService,
    evaluation_intelligence_overview_service,
)


EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE = (
    "evaluation_intelligence_overview"
)
EVALUATION_INTELLIGENCE_OVERVIEW_SCHEMA_VERSION = 1
EVALUATION_INTELLIGENCE_OVERVIEW_SOURCE = (
    "evaluation_intelligence_overview_projection_builder"
)
EVALUATION_INTELLIGENCE_OVERVIEW_DEPENDENCIES = (
    "evaluation_registry,evaluation_lineage,evaluation_coverage,"
    "evaluation_drift"
)


class EvaluationIntelligenceOverviewProjectionBuilderService(
    BaseProjectionBuilder[Any, EvaluationIntelligenceOverviewProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
        schema_version=EVALUATION_INTELLIGENCE_OVERVIEW_SCHEMA_VERSION,
        builder_name=(
            "EvaluationIntelligenceOverviewProjectionBuilderService"
        ),
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
            reconstruction_source=(
                EVALUATION_INTELLIGENCE_OVERVIEW_DEPENDENCIES
            ),
            authoritative_source=(
                EVALUATION_INTELLIGENCE_OVERVIEW_DEPENDENCIES
            ),
        ),
    )
    projection_type = EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE

    def __init__(
        self,
        overview: EvaluationIntelligenceOverviewService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._overview = overview or evaluation_intelligence_overview_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> EvaluationIntelligenceOverviewProjection:
        del source
        generated_at = self._clock()
        return self._overview.build_projection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_INTELLIGENCE_OVERVIEW_SOURCE,
            ),
            generated_at=generated_at,
        )


evaluation_intelligence_overview_projection_builder_service = (
    EvaluationIntelligenceOverviewProjectionBuilderService()
)
