from collections.abc import Sequence
from typing import Protocol, TypeVar, runtime_checkable

from app.models.projection import Projection, ProjectionSchemaInfo


SourceT = TypeVar("SourceT", contravariant=True)
ProjectionResultT = TypeVar(
    "ProjectionResultT",
    bound=Projection | Sequence[Projection],
    covariant=True,
)


@runtime_checkable
class BaseProjectionBuilder(Protocol[SourceT, ProjectionResultT]):
    schema_info: ProjectionSchemaInfo
    projection_type: str

    def build(self, source: SourceT) -> ProjectionResultT:
        """Build a fresh projection result without mutating source state."""
