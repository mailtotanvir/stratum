from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.decision_projection_builder_service import (
    decision_projection_builder_service,
)
from app.services.session_decision_projection_builder_service import (
    session_decision_projection_builder_service,
)


class ProjectionTypeAlreadyRegisteredError(ValueError):
    pass


class ProjectionTypeNotFoundError(LookupError):
    pass


class ProjectionRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, BaseProjectionBuilder] = {}

    def register(self, builder: BaseProjectionBuilder) -> None:
        projection_type = builder.projection_type
        if projection_type in self._builders:
            raise ProjectionTypeAlreadyRegisteredError(
                f"Projection type already registered: {projection_type}"
            )
        self._builders[projection_type] = builder

    def get(self, projection_type: str) -> BaseProjectionBuilder:
        try:
            return self._builders[projection_type]
        except KeyError as exc:
            raise ProjectionTypeNotFoundError(
                f"Projection type not found: {projection_type}"
            ) from exc

    def list_projection_types(self) -> list[str]:
        return sorted(self._builders)


projection_registry = ProjectionRegistry()
projection_registry.register(decision_projection_builder_service)
projection_registry.register(session_decision_projection_builder_service)
