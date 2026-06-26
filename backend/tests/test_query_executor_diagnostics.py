from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.query_catalog import QueryCatalog, QueryCatalogEntry
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_executor_diagnostics_service import (
    QueryExecutorDiagnosticsService,
)
from app.services.query_manifest_service import QueryManifestService
from app.services.projection_registry_service import projection_registry_service


EXPECTED_EXECUTABLE_QUERY_IDS = [
    "runtime.decision_effectiveness",
    "runtime.evaluation_coverage",
    "runtime.evaluation_drift",
    "runtime.evaluation_intelligence_overview",
    "runtime.evaluation_outcome_rollup",
    "runtime.evaluation_summary",
    "runtime.evaluation_trend",
    "runtime.governance_health_rollup",
    "runtime.policy_evaluation_overview",
    "runtime.policy_evidence",
    "runtime.policy_summary",
    "runtime.recommendation_outcome",
]

GOVERNANCE_INTELLIGENCE_QUERY_METADATA = {
    "decision_effectiveness": {
        "route": "/runtime/decision-effectiveness",
        "category": "decisions",
        "filters": [],
    },
    "evaluation_outcome_rollup": {
        "route": "/runtime/evaluation-outcome-rollup",
        "category": "evaluations",
        "filters": [
            "target_type",
            "target_id",
            "evaluation_type",
            "outcome",
        ],
    },
    "evaluation_summary": {
        "route": "/runtime/evaluation-summary",
        "category": "evaluations",
        "filters": [
            "target_type",
            "target_id",
            "evaluation_type",
            "outcome",
        ],
    },
    "evaluation_trend": {
        "route": "/runtime/evaluation-trend",
        "category": "evaluations",
        "filters": ["granularity"],
    },
    "governance_health_rollup": {
        "route": "/runtime/governance-health-rollup",
        "category": "governance",
        "filters": [],
    },
    "policy_evaluation_overview": {
        "route": "/runtime/policy-evaluation-overview",
        "category": "policies",
        "filters": [],
    },
    "recommendation_outcome": {
        "route": "/runtime/recommendation-outcomes",
        "category": "recommendations",
        "filters": [],
    },
}


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
    assert body["supported_query_count"] == 12
    assert body["catalog_query_count"] == 23
    assert "generated_at" in body


def test_supported_query_count_is_correct() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()

    assert diagnostics.supported_query_count == 12


def test_executable_query_ids_include_expected_supported_surfaces() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()

    assert diagnostics.executable_query_ids == EXPECTED_EXECUTABLE_QUERY_IDS


def test_governance_intelligence_queries_are_discoverable() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()
    catalog = QueryCatalogService().get_catalog()
    catalog_by_projection = {
        entry.projection_type: entry
        for entry in catalog.entries
    }

    for projection_type, expected in (
        GOVERNANCE_INTELLIGENCE_QUERY_METADATA.items()
    ):
        query_id = f"runtime.{projection_type}"

        assert query_id in diagnostics.executable_query_ids
        assert query_id not in diagnostics.unsupported_catalog_query_ids
        assert query_id not in diagnostics.missing_catalog_query_ids
        assert projection_type in catalog_by_projection
        assert catalog_by_projection[projection_type].route == (
            expected["route"]
        )
        assert catalog_by_projection[projection_type].category == (
            expected["category"]
        )
        assert catalog_by_projection[projection_type].filters == (
            expected["filters"]
        )


def test_governance_intelligence_query_metadata_is_consistent() -> None:
    catalog = QueryCatalogService().get_catalog()
    manifest = QueryManifestService().get_manifest()
    catalog_by_projection = {
        entry.projection_type: entry
        for entry in catalog.entries
    }
    manifest_by_projection = {
        entry.projection_type: entry
        for entry in manifest.entries
    }

    for projection_type, expected in (
        GOVERNANCE_INTELLIGENCE_QUERY_METADATA.items()
    ):
        registry_entry = projection_registry_service.get(projection_type)
        catalog_entry = catalog_by_projection[projection_type]
        manifest_entry = manifest_by_projection[projection_type]

        assert registry_entry.route == expected["route"]
        assert registry_entry.category == expected["category"]
        assert registry_entry.supported_filters == expected["filters"]
        assert registry_entry.capabilities.reconstructable is True
        assert registry_entry.capabilities.replayable is True
        assert catalog_entry.query_id == f"runtime.{projection_type}"
        assert catalog_entry.route == registry_entry.route
        assert catalog_entry.category == registry_entry.category
        assert catalog_entry.filters == registry_entry.supported_filters
        assert manifest_entry.query_id == catalog_entry.query_id
        assert manifest_entry.route == catalog_entry.route
        assert manifest_entry.category == catalog_entry.category
        assert manifest_entry.supported_filters == catalog_entry.filters
        assert manifest_entry.health_status == "healthy"
        assert manifest_entry.issues == []


def test_unsupported_catalog_query_ids_are_reported() -> None:
    diagnostics = QueryExecutorDiagnosticsService().get_diagnostics()

    assert diagnostics.unsupported_catalog_query_ids == [
        "runtime.artifact_lineage_projection",
        "runtime.decision_lineage_projection",
        "runtime.decision_projection",
        "runtime.evaluation_lineage",
        "runtime.evaluation_registry",
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
