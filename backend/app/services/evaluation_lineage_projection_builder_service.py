from datetime import UTC, datetime
from typing import Any, Callable

from app.models.evaluation_lineage import EvaluationLineageProjection
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_lineage_service import (
    EvaluationLineageService,
    evaluation_lineage_service,
)


EVALUATION_LINEAGE_PROJECTION_TYPE = "evaluation_lineage"
EVALUATION_LINEAGE_SCHEMA_VERSION = 1
EVALUATION_LINEAGE_SOURCE = "evaluation_lineage_projection_builder"


class EvaluationLineageProjectionBuilderService(
    BaseProjectionBuilder[Any, EvaluationLineageProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_LINEAGE_PROJECTION_TYPE,
        schema_version=EVALUATION_LINEAGE_SCHEMA_VERSION,
        builder_name="EvaluationLineageProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_LINEAGE_PROJECTION_TYPE,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = EVALUATION_LINEAGE_PROJECTION_TYPE

    def __init__(
        self,
        lineage: EvaluationLineageService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage = lineage or evaluation_lineage_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> EvaluationLineageProjection:
        del source
        generated_at = self._clock()
        return self._lineage.build_projection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_LINEAGE_SOURCE,
            ),
            generated_at=generated_at,
        )


evaluation_lineage_projection_builder_service = (
    EvaluationLineageProjectionBuilderService()
)
