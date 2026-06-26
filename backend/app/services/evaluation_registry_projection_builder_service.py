from datetime import UTC, datetime
from typing import Any, Callable

from app.models.evaluation_registry import EvaluationRegistryProjection
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_registry_service import (
    EvaluationRegistryService,
    evaluation_registry_service,
)


EVALUATION_REGISTRY_PROJECTION_TYPE = "evaluation_registry"
EVALUATION_REGISTRY_SCHEMA_VERSION = 1
EVALUATION_REGISTRY_SOURCE = "evaluation_registry_projection_builder"


class EvaluationRegistryProjectionBuilderService(
    BaseProjectionBuilder[Any, EvaluationRegistryProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_REGISTRY_PROJECTION_TYPE,
        schema_version=EVALUATION_REGISTRY_SCHEMA_VERSION,
        builder_name="EvaluationRegistryProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_REGISTRY_PROJECTION_TYPE,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = EVALUATION_REGISTRY_PROJECTION_TYPE

    def __init__(
        self,
        registry: EvaluationRegistryService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or evaluation_registry_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: Any = None,
    ) -> EvaluationRegistryProjection:
        del source
        generated_at = self._clock()
        return self._registry.build_projection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_REGISTRY_SOURCE,
            ),
            generated_at=generated_at,
        )


evaluation_registry_projection_builder_service = (
    EvaluationRegistryProjectionBuilderService()
)
