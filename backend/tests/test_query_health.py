from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.query_catalog import QueryCatalog, QueryCatalogEntry
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_health_service import QueryHealthService


class StaticCatalogService:
    def __init__(self, catalog: QueryCatalog) -> None:
        self._catalog = catalog

    def get_catalog(self) -> QueryCatalog:
        return self._catalog


def catalog_with(entries: list[QueryCatalogEntry]) -> QueryCatalog:
    return QueryCatalog(entries=entries, generated_at=datetime.now(UTC))


def entry(
    projection_type: str,
    route: str,
    category: str = "diagnostics",
    filters: list[str] | None = None,
) -> QueryCatalogEntry:
    return QueryCatalogEntry(
        query_id=f"runtime.{projection_type}",
        name=projection_type.replace("_", " ").title(),
        description="Test query surface.",
        projection_type=projection_type,
        route=route,
        category=category,
        filters=[] if filters is None else filters,
        rebuildable=True,
        persisted=True,
    )


def test_query_health_route_works() -> None:
    response = TestClient(app).get("/runtime/query-health")

    assert response.status_code == 200
    body = response.json()
    assert body["query_surface_count"] == 15
    assert body["registered_projection_count"] == 15
    assert "generated_at" in body


def test_healthy_catalog_returns_no_unhealthy_entries() -> None:
    health = QueryHealthService(QueryCatalogService()).get_health()

    assert health.query_surface_count == 15
    assert health.registered_projection_count == 15
    assert health.missing_route_count == 0
    assert health.missing_filter_metadata_count == 0
    assert health.duplicate_route_count == 0
    assert health.unhealthy_entries == []


def test_duplicate_routes_are_detected() -> None:
    service = QueryHealthService(
        StaticCatalogService(
            catalog_with(
                [
                    entry("first_projection", "/runtime/shared"),
                    entry("second_projection", "/runtime/shared"),
                ]
            )
        )
    )

    health = service.get_health()

    assert health.query_surface_count == 2
    assert health.registered_projection_count == 2
    assert health.duplicate_route_count == 2
    assert [item.query_id for item in health.unhealthy_entries] == [
        "runtime.first_projection",
        "runtime.second_projection",
    ]
    assert all(
        "duplicate_route" in item.issues
        for item in health.unhealthy_entries
    )


def test_missing_route_category_and_filter_metadata_are_detected() -> None:
    malformed = QueryCatalogEntry.model_construct(
        query_id="runtime.malformed_projection",
        name="Malformed Projection",
        description="Malformed metadata for tests.",
        projection_type="malformed_projection",
        route="",
        category="",
        filters=None,
        rebuildable=True,
        persisted=True,
    )
    service = QueryHealthService(
        StaticCatalogService(catalog_with([malformed]))
    )

    health = service.get_health()

    assert health.query_surface_count == 1
    assert health.registered_projection_count == 1
    assert health.missing_route_count == 1
    assert health.missing_filter_metadata_count == 1
    assert health.duplicate_route_count == 0
    assert len(health.unhealthy_entries) == 1
    assert health.unhealthy_entries[0].status == "unhealthy"
    assert health.unhealthy_entries[0].issues == [
        "missing_route",
        "missing_category",
        "missing_filter_metadata",
    ]


def test_duplicate_projection_types_count_as_one_registered_projection() -> None:
    service = QueryHealthService(
        StaticCatalogService(
            catalog_with(
                [
                    entry("same_projection", "/runtime/one"),
                    entry("same_projection", "/runtime/two"),
                ]
            )
        )
    )

    health = service.get_health()

    assert health.query_surface_count == 2
    assert health.registered_projection_count == 1
