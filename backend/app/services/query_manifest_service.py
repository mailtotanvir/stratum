from collections import defaultdict
from datetime import UTC, datetime

from app.models.query_catalog import QueryCatalog
from app.models.query_health import QueryHealth
from app.models.query_manifest import (
    QueryManifest,
    QueryManifestCategory,
    QueryManifestEntry,
)
from app.services.query_catalog_service import (
    QueryCatalogService,
    query_catalog_service,
)
from app.services.query_health_service import QueryHealthService


class QueryManifestService:
    def __init__(
        self,
        catalog_service: QueryCatalogService | None = None,
        health_service: QueryHealthService | None = None,
    ) -> None:
        self._catalog_service = catalog_service or query_catalog_service
        self._health_service = health_service or QueryHealthService(
            self._catalog_service
        )

    def get_manifest(self) -> QueryManifest:
        catalog = self._catalog_service.get_catalog()
        health = self._health_service.get_health()
        unhealthy_by_query_id = {
            entry.query_id: entry
            for entry in health.unhealthy_entries
        }

        entries = [
            QueryManifestEntry(
                query_id=entry.query_id,
                name=entry.name,
                description=entry.description,
                projection_type=entry.projection_type,
                category=entry.category,
                route=entry.route,
                supported_filters=entry.filters,
                rebuildable=entry.rebuildable,
                persisted=entry.persisted,
                health_status=(
                    "unhealthy"
                    if entry.query_id in unhealthy_by_query_id
                    else "healthy"
                ),
                issues=unhealthy_by_query_id.get(
                    entry.query_id
                ).issues
                if entry.query_id in unhealthy_by_query_id
                else [],
            )
            for entry in catalog.entries
        ]

        return QueryManifest(
            schema_version="1.0",
            generated_at=datetime.now(UTC),
            health_status=_overall_health_status(health),
            query_count=len(entries),
            categories=_category_summaries(catalog),
            entries=entries,
        )


def _category_summaries(
    catalog: QueryCatalog,
) -> list[QueryManifestCategory]:
    routes_by_category: dict[str, list[str]] = defaultdict(list)
    for entry in catalog.entries:
        routes_by_category[entry.category].append(entry.route)

    return [
        QueryManifestCategory(
            category=category,
            query_count=len(routes),
            routes=sorted(routes),
        )
        for category, routes in sorted(routes_by_category.items())
    ]


def _overall_health_status(
    health: QueryHealth,
) -> str:
    return "unhealthy" if health.unhealthy_entries else "healthy"


query_manifest_service = QueryManifestService()
