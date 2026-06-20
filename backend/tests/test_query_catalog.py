from fastapi.testclient import TestClient

from app.main import app
from app.services.projection_registry_service import (
    ProjectionRegistryService,
    default_projection_contracts,
)
from app.services.query_catalog_service import QueryCatalogService


EXPECTED_PROJECTION_TYPES = [
    "artifact_lineage_projection",
    "decision_lineage_projection",
    "decision_projection",
    "evaluation_outcome_rollup",
    "evaluation_summary",
    "evaluation_trend",
    "explainability",
    "governance_audit_projection",
    "operational_analytics",
    "policy_evaluation_overview",
    "policy_evidence",
    "policy_summary",
    "runtime_intelligence",
    "runtime_reconstruction_view",
    "session_decision_projection",
]


def test_query_catalog_returns_registered_projections() -> None:
    catalog = QueryCatalogService().get_catalog()

    assert [entry.projection_type for entry in catalog.entries] == (
        EXPECTED_PROJECTION_TYPES
    )
    assert [entry.query_id for entry in catalog.entries] == [
        f"runtime.{projection_type}"
        for projection_type in EXPECTED_PROJECTION_TYPES
    ]


def test_query_catalog_route_metadata_is_present() -> None:
    entries = {
        entry.projection_type: entry
        for entry in QueryCatalogService().get_catalog().entries
    }

    assert entries["evaluation_summary"].route == "/runtime/evaluation-summary"
    assert entries["evaluation_summary"].filters == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
    assert entries["evaluation_outcome_rollup"].route == (
        "/runtime/evaluation-outcome-rollup"
    )
    assert entries["evaluation_outcome_rollup"].filters == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
    assert entries["evaluation_trend"].route == "/runtime/evaluation-trend"
    assert entries["evaluation_trend"].filters == [
        "granularity",
    ]
    assert entries["policy_evaluation_overview"].route == (
        "/runtime/policy-evaluation-overview"
    )
    assert entries["policy_evaluation_overview"].filters == []
    assert entries["policy_evidence"].route == "/runtime/policy-evidence"
    assert entries["policy_evidence"].filters == [
        "policy_id",
        "evaluation_id",
        "evaluation_result_id",
        "target_type",
        "target_id",
        "evidence_type",
    ]


def test_query_catalog_categories_are_present() -> None:
    categories = {
        entry.category
        for entry in QueryCatalogService().get_catalog().entries
    }

    assert {
        "artifacts",
        "decisions",
        "evaluations",
        "policies",
        "governance",
        "observability",
    }.issubset(categories)


def test_query_catalog_uses_registry_metadata() -> None:
    registry = ProjectionRegistryService(
        initial_contracts=[
            {
                "projection_name": "custom_projection",
                "projection_version": 1,
                "projection_description": "Custom projection for tests.",
                "projection_owner": "tests",
                "projection_category": "diagnostics",
                "supports_replay": True,
                "supports_drift_detection": True,
                "supports_reconstruction": True,
                "supports_analytics": True,
                "supports_explainability": True,
            }
        ]
    )
    catalog = QueryCatalogService(registry).get_catalog()

    assert len(catalog.entries) == 1
    entry = catalog.entries[0]
    assert entry.query_id == "runtime.custom_projection"
    assert entry.name == "Custom Projection"
    assert entry.description == "Custom projection for tests."
    assert entry.projection_type == "custom_projection"
    assert entry.category == "diagnostics"
    assert entry.route == "/runtime/projections/custom_projection"
    assert entry.filters == []
    assert entry.rebuildable is True
    assert entry.persisted is True


def test_projection_registry_exposes_query_catalog_metadata() -> None:
    service = ProjectionRegistryService(
        initial_contracts=default_projection_contracts()
    )
    registry = service.list_registry()
    entries = {
        entry.projection_name: entry
        for entry in registry.projections
    }

    assert entries["policy_evidence"].projection_category == "policy"
    assert entries["policy_evidence"].category == "policies"
    assert entries["policy_evidence"].route == "/runtime/policy-evidence"
    assert entries["policy_evidence"].supported_filters == [
        "policy_id",
        "evaluation_id",
        "evaluation_result_id",
        "target_type",
        "target_id",
        "evidence_type",
    ]
    assert entries["evaluation_summary"].route == "/runtime/evaluation-summary"
    assert entries["evaluation_summary"].supported_filters == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
    assert entries["evaluation_outcome_rollup"].route == (
        "/runtime/evaluation-outcome-rollup"
    )
    assert entries["evaluation_outcome_rollup"].supported_filters == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
    assert entries["evaluation_trend"].route == "/runtime/evaluation-trend"
    assert entries["evaluation_trend"].supported_filters == ["granularity"]
    assert entries["policy_evaluation_overview"].route == (
        "/runtime/policy-evaluation-overview"
    )
    assert entries["policy_evaluation_overview"].supported_filters == []


def test_query_catalog_endpoint_returns_all_expected_projection_types() -> None:
    response = TestClient(app).get("/runtime/query-catalog")

    assert response.status_code == 200
    body = response.json()
    assert [entry["projection_type"] for entry in body["entries"]] == (
        EXPECTED_PROJECTION_TYPES
    )
    assert "generated_at" in body
    assert all(entry["route"] for entry in body["entries"])
    assert all(entry["category"] for entry in body["entries"])
