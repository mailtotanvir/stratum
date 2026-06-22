from app.runtime.projection_registry import projection_registry
from app.services.evaluation_diagnostics_service import (
    EvaluationDiagnosticsService,
)
from app.services.policy_diagnostics_service import PolicyDiagnosticsService
from app.services.projection_registry_service import projection_registry_service
from app.services.query_catalog_service import QueryCatalogService


GOVERNANCE_INTELLIGENCE_PROJECTIONS = {
    "decision_effectiveness": {
        "builder_name": "DecisionEffectivenessProjectionBuilderService",
        "authoritative_source": (
            "decision_records,runtime_evaluation_records"
        ),
        "route": "/runtime/decision-effectiveness",
        "category": "decisions",
        "filters": [],
    },
    "evaluation_outcome_rollup": {
        "builder_name": "EvaluationOutcomeRollupProjectionBuilderService",
        "authoritative_source": "runtime_evaluation_records",
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
        "builder_name": "EvaluationSummaryProjectionBuilderService",
        "authoritative_source": "runtime_evaluation_records",
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
        "builder_name": "EvaluationTrendProjectionBuilderService",
        "authoritative_source": "runtime_evaluation_records",
        "route": "/runtime/evaluation-trend",
        "category": "evaluations",
        "filters": ["granularity"],
    },
    "governance_health_rollup": {
        "builder_name": "GovernanceHealthRollupProjectionBuilderService",
        "authoritative_source": (
            "runtime_evaluation_records,"
            "planner_recommendations,"
            "decision_records,"
            "policies"
        ),
        "route": "/runtime/governance-health-rollup",
        "category": "governance",
        "filters": [],
    },
    "policy_evaluation_overview": {
        "builder_name": "PolicyEvaluationOverviewProjectionBuilderService",
        "authoritative_source": (
            "policies/policy_decisions/policy_violations/"
            "runtime_evaluation_records"
        ),
        "route": "/runtime/policy-evaluation-overview",
        "category": "policies",
        "filters": [],
    },
    "recommendation_outcome": {
        "builder_name": "RecommendationOutcomeProjectionBuilderService",
        "authoritative_source": (
            "planner_recommendations,"
            "decision_records,"
            "runtime_evaluation_records"
        ),
        "route": "/runtime/recommendation-outcomes",
        "category": "recommendations",
        "filters": [],
    },
}


def test_governance_intelligence_projection_schemas_are_registered() -> None:
    schemas = {
        schema.projection_type: schema
        for schema in projection_registry.list_schemas()
    }

    for projection_type, expected in (
        GOVERNANCE_INTELLIGENCE_PROJECTIONS.items()
    ):
        assert projection_type in schemas
        schema = schemas[projection_type]

        assert schema.builder_name == expected["builder_name"]
        assert schema.reconstruction.projection_type == projection_type
        assert schema.reconstruction.rebuildable is True
        assert schema.reconstruction.authoritative_source == (
            expected["authoritative_source"]
        )


def test_governance_intelligence_projection_metadata_matches_catalog() -> None:
    catalog = QueryCatalogService().get_catalog()
    catalog_by_projection = {
        entry.projection_type: entry
        for entry in catalog.entries
    }

    for projection_type, expected in (
        GOVERNANCE_INTELLIGENCE_PROJECTIONS.items()
    ):
        registry_entry = projection_registry_service.get(projection_type)
        catalog_entry = catalog_by_projection[projection_type]

        assert registry_entry.route == expected["route"]
        assert registry_entry.category == expected["category"]
        assert registry_entry.supported_filters == expected["filters"]
        assert registry_entry.capabilities.reconstructable is True
        assert registry_entry.capabilities.replayable is True
        assert registry_entry.capabilities.analyzable is True
        assert catalog_entry.query_id == f"runtime.{projection_type}"
        assert catalog_entry.route == registry_entry.route
        assert catalog_entry.category == registry_entry.category
        assert catalog_entry.filters == registry_entry.supported_filters
        assert catalog_entry.rebuildable is True


def test_evaluation_projection_diagnostics_use_governance_sources() -> None:
    diagnostics = EvaluationDiagnosticsService().generate()
    projections = {
        projection.projection_type: projection
        for projection in diagnostics.projections
    }

    for projection_type in (
        "evaluation_outcome_rollup",
        "evaluation_summary",
        "evaluation_trend",
    ):
        projection = projections[projection_type]

        assert projection.registered is True
        assert projection.rebuildable is True
        assert projection.persisted is False
        assert projection.source == "runtime_evaluation_records"
        assert projection.route == (
            GOVERNANCE_INTELLIGENCE_PROJECTIONS[projection_type]["route"]
        )


def test_policy_projection_diagnostics_use_governance_sources() -> None:
    diagnostics = PolicyDiagnosticsService().generate()
    projections = {
        projection.projection_type: projection
        for projection in diagnostics.projections
    }
    projection = projections["policy_evaluation_overview"]

    assert projection.registered is True
    assert projection.rebuildable is True
    assert projection.persisted is False
    assert projection.source == (
        GOVERNANCE_INTELLIGENCE_PROJECTIONS[
            "policy_evaluation_overview"
        ]["authoritative_source"]
    )
    assert projection.route == (
        GOVERNANCE_INTELLIGENCE_PROJECTIONS[
            "policy_evaluation_overview"
        ]["route"]
    )
