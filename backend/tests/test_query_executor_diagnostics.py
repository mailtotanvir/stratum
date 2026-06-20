from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.query_catalog import QueryCatalog, QueryCatalogEntry
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_executor_diagnostics_service import (
    QueryExecutorDiagnosticsService,
)


EXPECTED_EXECUTABLE_QUERY_IDS = [
    "runtime.decision_effectiveness",
    "runtime.evaluation_outcome_rollup",
    "runtime.evaluation_summary",
    "runtime.evaluation_trend",
    "runtime.governance_health_rollup",
    "runtime.policy_evaluation_overview",
    "runtime.policy_evidence",
    "runtime.policy_summary",
    "runtime.recommendation_outcome",
]


class StaticCatalogService:
    def __init__(self, catalog: QueryCatalog) -> None:
        self._catalog = catalog

    def get_catalog(self) -> QueryCatalog:
        return self._catalog


class StaticExecutorMetadata:
    def __init__(self, supported_projection_types: list[str]) -> None:
        self._supported_projection_types = supported_projection_types

    def supported_projection_types(self) -> list[str]:
        return self._supported_projection_types

    def execute(self, request):
        raise AssertionError("diagnostics must not execute queries")


def catalog_entry(projection_type: str) -> QueryCatalogEntry:
    return QueryCatalogEntry(
        query_id=f"runtime.{projection_type}",
        name=projection_type.replace("_", " ").title(),
        description="Test query surface.",
        projection_type=projection_type,
        category="diagnostics",
        route=f"/runtime/projections/{projection_type}",
        filters=[],
        rebuildable=True,
        persisted=True,
    )


def catalog_with(projection_types: list[str]) -> QueryCatalog:
    return QueryCatalog(
        entries=[
            catalog_entry(projection_type)
            for projection_type in projection_types
        ],
        generated_at=datetime.now(UTC),
    )


def test_query_executor_diagnostics_route_works() -> None:
    response = TestClient(app).get("/runtime/query-executor-diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["supported_query_count"] == 9
    assert body["catalog_query_count"] == 18
    assert "generated_at" in body


def test_supported_query_count_is_correct() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()

    assert diagnostics.supported_query_count == 9


def test_executable_query_ids_include_expected_supported_surfaces() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()

    assert diagnostics.executable_query_ids == EXPECTED_EXECUTABLE_QUERY_IDS


def test_unsupported_catalog_query_ids_are_reported() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()

    assert diagnostics.unsupported_catalog_query_ids == [
        "runtime.artifact_lineage_projection",
        "runtime.decision_lineage_projection",
        "runtime.decision_projection",
        "runtime.explainability",
        "runtime.governance_audit_projection",
        "runtime.operational_analytics",
        "runtime.runtime_intelligence",
        "runtime.runtime_reconstruction_view",
        "runtime.session_decision_projection",
    ]


def test_diagnostics_does_not_execute_projections() -> None:
    service = QueryExecutorDiagnosticsService(
        catalog_service=QueryCatalogService(),
        executor_service=StaticExecutorMetadata(
            ["evaluation_summary", "policy_summary"]
        ),
    )

    diagnostics = service.get_diagnostics()

    assert diagnostics.executable_query_ids == [
        "runtime.evaluation_summary",
        "runtime.policy_summary",
    ]


def test_missing_catalog_query_ids_logic() -> None:
    service = QueryExecutorDiagnosticsService(
        catalog_service=StaticCatalogService(
            catalog_with(["evaluation_summary"])
        ),
        executor_service=StaticExecutorMetadata(
            ["evaluation_summary", "policy_summary"]
        ),
    )

    diagnostics = service.get_diagnostics()

    assert diagnostics.catalog_query_count == 1
    assert diagnostics.supported_query_count == 2
    assert diagnostics.executable_query_ids == [
        "runtime.evaluation_summary"
    ]
    assert diagnostics.unsupported_catalog_query_ids == []
    assert diagnostics.missing_catalog_query_ids == [
        "runtime.policy_summary"
    ]
