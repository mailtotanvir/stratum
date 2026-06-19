from datetime import UTC, datetime
from typing import Protocol

from app.models.query_catalog import QueryCatalog
from app.models.query_executor_diagnostics import (
    QueryExecutorDiagnostics,
    QueryExecutorDispatchDiagnostic,
)
from app.services.query_catalog_service import (
    QueryCatalogService,
    query_catalog_service,
)
from app.services.query_executor_service import (
    QueryExecutorService,
    query_executor_service,
)


class CatalogProvider(Protocol):
    def get_catalog(self) -> QueryCatalog:
        ...


class ExecutorMetadataProvider(Protocol):
    def supported_projection_types(self) -> list[str]:
        ...


class QueryExecutorDiagnosticsService:
    def __init__(
        self,
        catalog_service: CatalogProvider | None = None,
        executor_service: ExecutorMetadataProvider | None = None,
    ) -> None:
        self._catalog_service = catalog_service or query_catalog_service
        self._executor_service = executor_service or query_executor_service

    def get_diagnostics(self) -> QueryExecutorDiagnostics:
        catalog = self._catalog_service.get_catalog()
        supported_projection_types = set(
            self._executor_service.supported_projection_types()
        )
        catalog_by_projection_type = {
            entry.projection_type: entry
            for entry in catalog.entries
        }

        dispatch_diagnostics = [
            QueryExecutorDispatchDiagnostic(
                query_id=entry.query_id,
                projection_type=entry.projection_type,
                route=entry.route,
                executable=entry.projection_type
                in supported_projection_types,
                reason=(
                    "registered_dispatch"
                    if entry.projection_type in supported_projection_types
                    else "not_registered_for_execution"
                ),
            )
            for entry in catalog.entries
        ]
        executable_query_ids = sorted(
            diagnostic.query_id
            for diagnostic in dispatch_diagnostics
            if diagnostic.executable
        )
        unsupported_catalog_query_ids = sorted(
            diagnostic.query_id
            for diagnostic in dispatch_diagnostics
            if not diagnostic.executable
        )
        missing_catalog_query_ids = sorted(
            f"runtime.{projection_type}"
            for projection_type in supported_projection_types
            if projection_type not in catalog_by_projection_type
        )

        return QueryExecutorDiagnostics(
            supported_query_count=len(supported_projection_types),
            catalog_query_count=len(catalog.entries),
            executable_query_ids=executable_query_ids,
            unsupported_catalog_query_ids=unsupported_catalog_query_ids,
            missing_catalog_query_ids=missing_catalog_query_ids,
            generated_at=datetime.now(UTC),
        )


query_executor_diagnostics_service = QueryExecutorDiagnosticsService(
    QueryCatalogService(),
    QueryExecutorService(),
)
