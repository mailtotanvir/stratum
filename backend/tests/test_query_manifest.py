from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.query_catalog import QueryCatalog, QueryCatalogEntry
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_manifest_service import QueryManifestService


EXPECTED_PROJECTION_TYPES = [
    "artifact_lineage_projection",
    "decision_effectiveness",
    "decision_lineage_projection",
    "decision_projection",
    "evaluation_coverage",
    "evaluation_drift",
    "evaluation_intelligence_overview",
    "evaluation_lineage",
    "evaluation_outcome_rollup",
    "evaluation_registry",
    "evaluation_summary",
    "evaluation_trend",
    "explainability",
    "governance_audit_projection",
    "governance_health_rollup",
    "operational_analytics",
    "policy_evaluation_overview",
    "policy_evidence",
    "policy_summary",
    "recommendation_outcome",
    "runtime_intelligence",
    "runtime_reconstruction_view",
    "session_decision_projection",
]


class StaticCatalogService:
    def __init__(self, catalog: QueryCatalog) -> None:
        self._catalog = catalog

    def get_catalog(self) -> QueryCatalog:
        return self._catalog


def test_query_manifest_route_works() -> None:
    response = TestClient(app).get("/runtime/query-manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["query_count"] == 23
    assert body["health_status"] == "healthy"
    assert "generated_at" in body


def test_query_manifest_query_count_matches_catalog_entries() -> None:
    catalog = QueryCatalogService().get_catalog()
    manifest = QueryManifestService().get_manifest()

    assert manifest.query_count == len(catalog.entries)
    assert len(manifest.entries) == len(catalog.entries)


def test_query_manifest_categories_summarize_routes() -> None:
    manifest = QueryManifestService().get_manifest()
    categories = {
        category.category: category
        for category in manifest.categories
    }

    assert categories["policies"].query_count == 3
    assert categories["policies"].routes == [
        "/runtime/policy-evaluation-overview",
        "/runtime/policy-evidence",
        "/runtime/policy-projections",
    ]
    assert categories["decisions"].query_count == 4
    assert categories["decisions"].routes == [
        "/runtime/decision-effectiveness",
        "/runtime/decision-lineage",
        "/runtime/projections/decision_projection",
        "/runtime/projections/session_decision_projection",
    ]
    assert categories["evaluations"].query_count == 8
    assert categories["evaluations"].routes == [
        "/evaluation-coverage/projection",
        "/evaluation-drift/projection",
        "/evaluation-intelligence-overview/projection",
        "/evaluation-lineage/projection",
        "/evaluation-registry/projection",
        "/runtime/evaluation-outcome-rollup",
        "/runtime/evaluation-summary",
        "/runtime/evaluation-trend",
    ]
    assert categories["governance"].query_count == 2
    assert categories["governance"].routes == [
        "/runtime/governance-health-rollup",
        "/runtime/governance/audit",
    ]
    assert categories["recommendations"].query_count == 1
    assert categories["recommendations"].routes == [
        "/runtime/recommendation-outcomes"
    ]


def test_query_manifest_entry_health_is_included() -> None:
    catalog = QueryCatalog(
        entries=[
            QueryCatalogEntry(
                query_id="runtime.first_projection",
                name="First Projection",
                description="First test projection.",
                projection_type="first_projection",
                category="diagnostics",
                route="/runtime/shared",
                filters=[],
                rebuildable=True,
                persisted=True,
            ),
            QueryCatalogEntry(
                query_id="runtime.second_projection",
                name="Second Projection",
                description="Second test projection.",
                projection_type="second_projection",
                category="diagnostics",
                route="/runtime/shared",
                filters=[],
                rebuildable=True,
                persisted=True,
            ),
        ],
        generated_at=datetime.now(UTC),
    )

    manifest = QueryManifestService(
        StaticCatalogService(catalog)
    ).get_manifest()

    assert manifest.health_status == "unhealthy"
    assert [entry.health_status for entry in manifest.entries] == [
        "unhealthy",
        "unhealthy",
    ]
    assert all(
        entry.issues == ["duplicate_route"]
        for entry in manifest.entries
    )


def test_expected_projections_appear_in_manifest() -> None:
    manifest = QueryManifestService().get_manifest()

    assert [entry.projection_type for entry in manifest.entries] == (
        EXPECTED_PROJECTION_TYPES
    )
    entries = {
        entry.projection_type: entry
        for entry in manifest.entries
    }
    assert entries["decision_effectiveness"].query_id == (
        "runtime.decision_effectiveness"
    )
    assert entries["decision_effectiveness"].route == (
        "/runtime/decision-effectiveness"
    )
    assert entries["decision_effectiveness"].supported_filters == []
    assert entries["policy_evidence"].supported_filters == [
        "policy_id",
        "evaluation_id",
        "evaluation_result_id",
        "target_type",
        "target_id",
        "evidence_type",
    ]
    assert entries["evaluation_coverage"].query_id == (
        "runtime.evaluation_coverage"
    )
    assert entries["evaluation_coverage"].route == (
        "/evaluation-coverage/projection"
    )
    assert entries["evaluation_coverage"].supported_filters == []
    assert entries["evaluation_drift"].query_id == (
        "runtime.evaluation_drift"
    )
    assert entries["evaluation_drift"].route == (
        "/evaluation-drift/projection"
    )
    assert entries["evaluation_drift"].supported_filters == []
    assert entries["evaluation_intelligence_overview"].query_id == (
        "runtime.evaluation_intelligence_overview"
    )
    assert entries["evaluation_intelligence_overview"].route == (
        "/evaluation-intelligence-overview/projection"
    )
    assert entries["evaluation_intelligence_overview"].supported_filters == []
    assert entries["evaluation_lineage"].query_id == (
        "runtime.evaluation_lineage"
    )
    assert entries["evaluation_lineage"].route == (
        "/evaluation-lineage/projection"
    )
    assert entries["evaluation_lineage"].supported_filters == []
    assert entries["evaluation_summary"].query_id == "runtime.evaluation_summary"
    assert entries["evaluation_summary"].route == "/runtime/evaluation-summary"
    assert entries["evaluation_summary"].supported_filters == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
    assert entries["evaluation_outcome_rollup"].query_id == (
        "runtime.evaluation_outcome_rollup"
    )
    assert entries["evaluation_outcome_rollup"].route == (
        "/runtime/evaluation-outcome-rollup"
    )
    assert entries["evaluation_outcome_rollup"].supported_filters == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
    assert entries["evaluation_registry"].query_id == (
        "runtime.evaluation_registry"
    )
    assert entries["evaluation_registry"].route == (
        "/evaluation-registry/projection"
    )
    assert entries["evaluation_registry"].supported_filters == []
    assert entries["evaluation_trend"].query_id == "runtime.evaluation_trend"
    assert entries["evaluation_trend"].route == "/runtime/evaluation-trend"
    assert entries["evaluation_trend"].supported_filters == ["granularity"]
    assert entries["governance_health_rollup"].query_id == (
        "runtime.governance_health_rollup"
    )
    assert entries["governance_health_rollup"].route == (
        "/runtime/governance-health-rollup"
    )
    assert entries["governance_health_rollup"].supported_filters == []
    assert entries["policy_evaluation_overview"].query_id == (
        "runtime.policy_evaluation_overview"
    )
    assert entries["policy_evaluation_overview"].route == (
        "/runtime/policy-evaluation-overview"
    )
    assert entries["policy_evaluation_overview"].supported_filters == []
    assert entries["recommendation_outcome"].query_id == (
        "runtime.recommendation_outcome"
    )
    assert entries["recommendation_outcome"].route == (
        "/runtime/recommendation-outcomes"
    )
    assert entries["recommendation_outcome"].supported_filters == []


def test_query_manifest_health_status_is_healthy_when_catalog_is_healthy() -> None:
    manifest = QueryManifestService().get_manifest()

    assert manifest.health_status == "healthy"
    assert all(entry.health_status == "healthy" for entry in manifest.entries)
    assert all(entry.issues == [] for entry in manifest.entries)
