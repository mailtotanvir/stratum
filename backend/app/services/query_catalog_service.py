from datetime import UTC, datetime

from app.models.query_catalog import QueryCatalog, QueryCatalogEntry
from app.services.projection_registry_service import (
    ProjectionRegistryService,
    projection_registry_service,
)


EXCLUDED_QUERY_PROJECTIONS = {
    "repository_memory",
    "session_memory",
    "working_memory",
}


class QueryCatalogService:
    def __init__(
        self,
        registry: ProjectionRegistryService | None = None,
    ) -> None:
        self._registry = registry or projection_registry_service

    def get_catalog(self) -> QueryCatalog:
        registry = self._registry.list_registry()
        entries = [
            QueryCatalogEntry(
                query_id=f"runtime.{entry.projection_name}",
                name=_display_name(entry.projection_name),
                description=entry.contract.projection_description,
                projection_type=entry.projection_name,
                route=entry.route,
                category=entry.category,
                filters=entry.supported_filters,
                rebuildable=entry.capabilities.reconstructable,
                persisted=True,
            )
            for entry in registry.projections
            if entry.projection_name not in EXCLUDED_QUERY_PROJECTIONS
        ]
        return QueryCatalog(
            entries=entries,
            generated_at=datetime.now(UTC),
        )


def _display_name(projection_name: str) -> str:
    return projection_name.replace("_", " ").title()


query_catalog_service = QueryCatalogService()
