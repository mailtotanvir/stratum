from datetime import UTC, datetime
from typing import Any, Callable

from app.models.evaluation_drift import EvaluationDriftProjection
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_drift_service import (
    EvaluationDriftService,
    evaluation_drift_service,
)


EVALUATION_DRIFT_PROJECTION_TYPE = "evaluation_drift"
EVALUATION_DRIFT_SCHEMA_VERSION = 1
EVALUATION_DRIFT_SOURCE = "evaluation_drift_projection_builder"


class EvaluationDriftProjectionBuilderService(
    BaseProjectionBuilder[Any, EvaluationDriftProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_DRIFT_PROJECTION_TYPE,
        schema_version=EVALUATION_DRIFT_SCHEMA_VERSION,
        builder_name="EvaluationDriftProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_DRIFT_PROJECTION_TYPE,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = EVALUATION_DRIFT_PROJECTION_TYPE

    def __init__(
        self,
        drift: EvaluationDriftService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._drift = drift or evaluation_drift_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> EvaluationDriftProjection:
        del source
        generated_at = self._clock()
        return self._drift.build_projection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_DRIFT_SOURCE,
            ),
            generated_at=generated_at,
        )


evaluation_drift_projection_builder_service = (
    EvaluationDriftProjectionBuilderService()
)
