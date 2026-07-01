from collections import Counter
from datetime import UTC, datetime
from typing import Protocol

from app.models.query_catalog import QueryCatalog
from app.models.query_health import QueryHealth, QueryHealthEntry
from app.services.query_catalog_service import (
    QueryCatalogService,
    query_catalog_service,
)


class CatalogProvider(Protocol):
    def get_catalog(self) -> QueryCatalog:
        ...


class QueryHealthService:
    def __init__(
        self,
        catalog_service: CatalogProvider | None = None,
    ) -> None:
        self._catalog_service = catalog_service or query_catalog_service
        self._cached_signature: tuple[tuple[str, str, str, tuple[str, ...]], ...] | None = None
        self._cached_health: QueryHealth | None = None

    def get_health(self) -> QueryHealth:
        catalog = self._catalog_service.get_catalog()
        signature = tuple(
            (
                entry.query_id,
                entry.projection_type,
                entry.route,
                tuple(entry.filters or []),
            )
            for entry in catalog.entries
        )
        if signature == self._cached_signature and self._cached_health is not None:
            return self._cached_health

        route_counts = Counter(
            entry.route
            for entry in catalog.entries
            if isinstance(entry.route, str) and entry.route.strip()
        )
        unhealthy_entries: list[QueryHealthEntry] = []
        missing_route_count = 0
        missing_filter_metadata_count = 0
        duplicate_route_count = 0

        for entry in catalog.entries:
            issues: list[str] = []
            route = entry.route if isinstance(entry.route, str) else ""
            category = entry.category if isinstance(entry.category, str) else ""
            filters = getattr(entry, "filters", None)

            if not route.strip():
                issues.append("missing_route")
                missing_route_count += 1
            if not category.strip():
                issues.append("missing_category")
            if not isinstance(filters, list):
                issues.append("missing_filter_metadata")
                missing_filter_metadata_count += 1
            if route.strip() and route_counts[route] > 1:
                issues.append("duplicate_route")
                duplicate_route_count += 1

            if issues:
                unhealthy_entries.append(
                    QueryHealthEntry(
                        query_id=entry.query_id,
                        projection_type=entry.projection_type,
                        route=route,
                        status="unhealthy",
                        issues=issues,
                    )
                )

        health = QueryHealth(
            query_surface_count=len(catalog.entries),
            registered_projection_count=len(
                {entry.projection_type for entry in catalog.entries}
            ),
            missing_route_count=missing_route_count,
            missing_filter_metadata_count=missing_filter_metadata_count,
            duplicate_route_count=duplicate_route_count,
            unhealthy_entries=unhealthy_entries,
            generated_at=datetime.now(UTC),
        )
        self._cached_signature = signature
        self._cached_health = health
        return health


query_health_service = QueryHealthService(QueryCatalogService())
