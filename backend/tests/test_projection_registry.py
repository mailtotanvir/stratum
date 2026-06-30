import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.runtime.projection_registry import (
    ProjectionContractError,
    ProjectionRegistry,
    ProjectionTypeAlreadyRegisteredError,
    ProjectionTypeNotFoundError,
    projection_registry,
)
from app.services.decision_projection_builder_service import (
    DECISION_PROJECTION_SCHEMA_VERSION,
    DECISION_PROJECTION_TYPE,
    decision_projection_builder_service,
)
from app.services.artifact_lineage_projection_builder_service import (
    ARTIFACT_LINEAGE_PROJECTION_TYPE,
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    artifact_lineage_projection_builder,
)
from app.services.decision_lineage_projection_builder_service import (
    DECISION_LINEAGE_PROJECTION_TYPE,
    DECISION_LINEAGE_SCHEMA_VERSION,
    decision_lineage_projection_builder,
)
from app.services.decision_effectiveness_projection_builder_service import (
    DECISION_EFFECTIVENESS_PROJECTION_TYPE,
    DECISION_EFFECTIVENESS_SCHEMA_VERSION,
    decision_effectiveness_projection_builder_service,
)
from app.services.evaluation_coverage_projection_builder_service import (
    EVALUATION_COVERAGE_PROJECTION_TYPE,
    EVALUATION_COVERAGE_SCHEMA_VERSION,
    evaluation_coverage_projection_builder_service,
)
from app.services.evaluation_drift_projection_builder_service import (
    EVALUATION_DRIFT_PROJECTION_TYPE,
    EVALUATION_DRIFT_SCHEMA_VERSION,
    evaluation_drift_projection_builder_service,
)
from app.services.evaluation_intelligence_overview_projection_builder_service import (
    EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
    EVALUATION_INTELLIGENCE_OVERVIEW_SCHEMA_VERSION,
    evaluation_intelligence_overview_projection_builder_service,
)
from app.services.evaluation_summary_projection_builder_service import (
    EVALUATION_SUMMARY_SCHEMA_VERSION,
    EVALUATION_SUMMARY_PROJECTION_TYPE,
    evaluation_summary_projection_builder_service,
)
from app.services.evaluation_trend_projection_v2_builder_service import (
    EVALUATION_TREND_PROJECTION_TYPE,
    EVALUATION_TREND_SCHEMA_VERSION,
    evaluation_trend_projection_builder_service,
)
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
    EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION,
    evaluation_outcome_rollup_projection_builder_service,
)
from app.services.evaluation_lineage_projection_builder_service import (
    EVALUATION_LINEAGE_PROJECTION_TYPE,
    EVALUATION_LINEAGE_SCHEMA_VERSION,
    evaluation_lineage_projection_builder_service,
)
from app.services.evaluation_registry_projection_builder_service import (
    EVALUATION_REGISTRY_PROJECTION_TYPE,
    EVALUATION_REGISTRY_SCHEMA_VERSION,
    evaluation_registry_projection_builder_service,
)
from app.services.event_service import event_service
from app.services.governance_audit_projection_builder_service import (
    GOVERNANCE_AUDIT_PROJECTION_TYPE,
    GOVERNANCE_AUDIT_SCHEMA_VERSION,
    governance_audit_projection_builder,
)
from app.services.governance_health_rollup_projection_builder_service import (
    GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
    GOVERNANCE_HEALTH_ROLLUP_SCHEMA_VERSION,
    governance_health_rollup_projection_builder_service,
)
from app.services.policy_evidence_projection_builder_service import (
    POLICY_EVIDENCE_PROJECTION_TYPE,
    POLICY_EVIDENCE_SCHEMA_VERSION,
    policy_evidence_projection_builder_service,
)
from app.services.policy_evaluation_overview_projection_builder_service import (
    POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
    POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION,
    policy_evaluation_overview_projection_builder_service,
)
from app.services.policy_projection_builder_service import (
    POLICY_SUMMARY_PROJECTION_TYPE,
    POLICY_SUMMARY_SCHEMA_VERSION,
    policy_projection_builder_service,
)
from app.services.recommendation_outcome_projection_builder_service import (
    RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
    RECOMMENDATION_OUTCOME_SCHEMA_VERSION,
    recommendation_outcome_projection_builder_service,
)
from app.services.session_agent_execution_projection_builder_service import (
    SESSION_AGENT_EXECUTION_PROJECTION_SCHEMA_VERSION,
    SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
    session_agent_execution_projection_builder_service,
)
from app.services.session_decision_projection_builder_service import (
    SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
    SESSION_DECISION_PROJECTION_TYPE,
    session_decision_projection_builder_service,
)

MISSING = object()


class RecordingProjectionBuilder:
    def __init__(
        self,
        projection_type: str,
        schema_version: int = 1,
    ) -> None:
        self.projection_type = projection_type
        self.schema_info = ProjectionSchemaInfo(
            projection_type=projection_type,
            schema_version=schema_version,
            builder_name=type(self).__name__,
            reconstruction=ProjectionReconstructionInfo(
                projection_type=projection_type,
                reconstruction_source="test_state",
                authoritative_source="test_source",
            ),
        )
        self.build_calls: list[str] = []

    def build(self, source: str):
        self.build_calls.append(source)
        raise AssertionError("the registry must not build projections")


class RawContractProjectionBuilder:
    projection_type = "raw_projection"

    def __init__(self, schema_info: dict) -> None:
        self.schema_info = schema_info

    def build(self, source: str):
        raise AssertionError("contract validation must not build projections")


def valid_raw_contract() -> dict:
    return {
        "projection_type": "raw_projection",
        "schema_version": 1,
        "builder_name": "RawContractProjectionBuilder",
        "reconstruction": {
            "projection_type": "raw_projection",
            "reconstruction_source": "runtime_session_state",
            "rebuildable": True,
            "authoritative_source": "runtime_session",
        },
    }


def test_projection_builders_register_and_lookup_by_unique_type() -> None:
    registry = ProjectionRegistry()
    decision_builder = RecordingProjectionBuilder("decision_projection")
    session_builder = RecordingProjectionBuilder(
        "session_decision_projection"
    )

    registry.register(decision_builder)
    registry.register(session_builder)

    assert registry.list_projection_types() == [
        "decision_projection",
        "session_decision_projection",
    ]
    assert registry.get("decision_projection") is decision_builder
    assert registry.get("session_decision_projection") is session_builder
    assert registry.list_schemas() == [
        decision_builder.schema_info,
        session_builder.schema_info,
    ]
    assert decision_builder.build_calls == []
    assert session_builder.build_calls == []


def test_valid_raw_projection_contract_registers_successfully() -> None:
    registry = ProjectionRegistry()
    builder = RawContractProjectionBuilder(valid_raw_contract())

    registry.register(builder)

    assert registry.get("raw_projection") is builder
    assert registry.get_schema("raw_projection").model_dump() == (
        valid_raw_contract()
    )


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    [
        pytest.param(
            ("projection_type",),
            "",
            id="missing-projection-type",
        ),
        pytest.param(
            ("schema_version",),
            MISSING,
            id="missing-schema-version",
        ),
        pytest.param(
            ("builder_name",),
            "",
            id="missing-builder-name",
        ),
        pytest.param(
            ("reconstruction", "reconstruction_source"),
            "",
            id="missing-reconstruction-source",
        ),
        pytest.param(
            ("reconstruction", "authoritative_source"),
            "",
            id="missing-authoritative-source",
        ),
        pytest.param(
            ("reconstruction", "rebuildable"),
            False,
            id="not-rebuildable",
        ),
    ],
)
def test_invalid_projection_contract_is_rejected(
    field_path: tuple[str, ...],
    invalid_value,
) -> None:
    contract = valid_raw_contract()
    target = contract
    for field_name in field_path[:-1]:
        target = target[field_name]
    if invalid_value is MISSING:
        del target[field_path[-1]]
    else:
        target[field_path[-1]] = invalid_value
    registry = ProjectionRegistry()

    with pytest.raises(ProjectionContractError):
        registry.register(RawContractProjectionBuilder(contract))

    assert registry.list_projection_types() == []


def test_projection_types_must_be_unique() -> None:
    registry = ProjectionRegistry()
    registry.register(RecordingProjectionBuilder("decision_projection"))

    with pytest.raises(
        ProjectionTypeAlreadyRegisteredError,
        match="Projection type already registered: decision_projection",
    ):
        registry.register(RecordingProjectionBuilder("decision_projection"))


def test_unknown_projection_lookup_raises_predictable_error() -> None:
    registry = ProjectionRegistry()

    with pytest.raises(
        ProjectionTypeNotFoundError,
        match="Projection type not found: missing_projection",
    ):
        registry.get("missing_projection")


def test_runtime_registry_contains_existing_builders() -> None:
    assert projection_registry.list_projection_types() == [
        ARTIFACT_LINEAGE_PROJECTION_TYPE,
        DECISION_EFFECTIVENESS_PROJECTION_TYPE,
        DECISION_LINEAGE_PROJECTION_TYPE,
        DECISION_PROJECTION_TYPE,
        EVALUATION_COVERAGE_PROJECTION_TYPE,
        EVALUATION_DRIFT_PROJECTION_TYPE,
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
        EVALUATION_LINEAGE_PROJECTION_TYPE,
        EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
        EVALUATION_REGISTRY_PROJECTION_TYPE,
        EVALUATION_SUMMARY_PROJECTION_TYPE,
        EVALUATION_TREND_PROJECTION_TYPE,
        GOVERNANCE_AUDIT_PROJECTION_TYPE,
        GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
        POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
        POLICY_EVIDENCE_PROJECTION_TYPE,
        POLICY_SUMMARY_PROJECTION_TYPE,
        RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
        "repository_memory",
        SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
        SESSION_DECISION_PROJECTION_TYPE,
        "session_memory",
        "working_memory",
    ]
    assert (
        projection_registry.get(ARTIFACT_LINEAGE_PROJECTION_TYPE)
        is artifact_lineage_projection_builder
    )
    assert (
        projection_registry.get(DECISION_EFFECTIVENESS_PROJECTION_TYPE)
        is decision_effectiveness_projection_builder_service
    )
    assert (
        projection_registry.get(DECISION_LINEAGE_PROJECTION_TYPE)
        is decision_lineage_projection_builder
    )
    assert (
        projection_registry.get(DECISION_PROJECTION_TYPE)
        is decision_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_COVERAGE_PROJECTION_TYPE)
        is evaluation_coverage_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_DRIFT_PROJECTION_TYPE)
        is evaluation_drift_projection_builder_service
    )
    assert (
        projection_registry.get(
            EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
        )
        is evaluation_intelligence_overview_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_LINEAGE_PROJECTION_TYPE)
        is evaluation_lineage_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE)
        is evaluation_outcome_rollup_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_REGISTRY_PROJECTION_TYPE)
        is evaluation_registry_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_SUMMARY_PROJECTION_TYPE)
        is evaluation_summary_projection_builder_service
    )
    assert (
        projection_registry.get(EVALUATION_TREND_PROJECTION_TYPE)
        is evaluation_trend_projection_builder_service
    )
    assert (
        projection_registry.get(GOVERNANCE_AUDIT_PROJECTION_TYPE)
        is governance_audit_projection_builder
    )
    assert (
        projection_registry.get(GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE)
        is governance_health_rollup_projection_builder_service
    )
    assert (
        projection_registry.get(POLICY_EVIDENCE_PROJECTION_TYPE)
        is policy_evidence_projection_builder_service
    )
    assert (
        projection_registry.get(POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE)
        is policy_evaluation_overview_projection_builder_service
    )
    assert (
        projection_registry.get(POLICY_SUMMARY_PROJECTION_TYPE)
        is policy_projection_builder_service
    )
    assert (
        projection_registry.get(RECOMMENDATION_OUTCOME_PROJECTION_TYPE)
        is recommendation_outcome_projection_builder_service
    )
    assert (
        projection_registry.get(SESSION_AGENT_EXECUTION_PROJECTION_TYPE)
        is session_agent_execution_projection_builder_service
    )
    assert (
        projection_registry.get(SESSION_DECISION_PROJECTION_TYPE)
        is session_decision_projection_builder_service
    )
    assert not hasattr(projection_registry, "build")


def test_runtime_registry_exposes_stable_schema_contracts() -> None:
    schemas = projection_registry.list_schemas()

    assert [schema.model_dump() for schema in schemas] == [
        {
            "projection_type": ARTIFACT_LINEAGE_PROJECTION_TYPE,
            "schema_version": ARTIFACT_LINEAGE_SCHEMA_VERSION,
            "builder_name": "ArtifactLineageProjectionBuilder",
            "reconstruction": {
                "projection_type": ARTIFACT_LINEAGE_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": DECISION_EFFECTIVENESS_PROJECTION_TYPE,
            "schema_version": DECISION_EFFECTIVENESS_SCHEMA_VERSION,
            "builder_name": "DecisionEffectivenessProjectionBuilderService",
            "reconstruction": {
                "projection_type": DECISION_EFFECTIVENESS_PROJECTION_TYPE,
                "reconstruction_source": (
                    "decision_records,evaluation_records"
                ),
                "rebuildable": True,
                "authoritative_source": (
                    "decision_records,runtime_evaluation_records"
                ),
            },
        },
        {
            "projection_type": DECISION_LINEAGE_PROJECTION_TYPE,
            "schema_version": DECISION_LINEAGE_SCHEMA_VERSION,
            "builder_name": "DecisionLineageProjectionBuilder",
            "reconstruction": {
                "projection_type": DECISION_LINEAGE_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": DECISION_PROJECTION_TYPE,
            "schema_version": DECISION_PROJECTION_SCHEMA_VERSION,
            "builder_name": "DecisionProjectionBuilderService",
            "reconstruction": {
                "projection_type": DECISION_PROJECTION_TYPE,
                "reconstruction_source": "runtime_session_state",
                "rebuildable": True,
                "authoritative_source": "runtime_session",
            },
        },
        {
            "projection_type": EVALUATION_COVERAGE_PROJECTION_TYPE,
            "schema_version": EVALUATION_COVERAGE_SCHEMA_VERSION,
            "builder_name": "EvaluationCoverageProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_COVERAGE_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": EVALUATION_DRIFT_PROJECTION_TYPE,
            "schema_version": EVALUATION_DRIFT_SCHEMA_VERSION,
            "builder_name": "EvaluationDriftProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_DRIFT_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
            "schema_version": EVALUATION_INTELLIGENCE_OVERVIEW_SCHEMA_VERSION,
            "builder_name": (
                "EvaluationIntelligenceOverviewProjectionBuilderService"
            ),
            "reconstruction": {
                "projection_type": (
                    EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
                ),
                "reconstruction_source": (
                    "evaluation_registry,evaluation_lineage,"
                    "evaluation_coverage,evaluation_drift"
                ),
                "rebuildable": True,
                "authoritative_source": (
                    "evaluation_registry,evaluation_lineage,"
                    "evaluation_coverage,evaluation_drift"
                ),
            },
        },
        {
            "projection_type": EVALUATION_LINEAGE_PROJECTION_TYPE,
            "schema_version": EVALUATION_LINEAGE_SCHEMA_VERSION,
            "builder_name": "EvaluationLineageProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_LINEAGE_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
            "schema_version": EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION,
            "builder_name": "EvaluationOutcomeRollupProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
                "reconstruction_source": "evaluation_records",
                "rebuildable": True,
                "authoritative_source": "runtime_evaluation_records",
            },
        },
        {
            "projection_type": EVALUATION_REGISTRY_PROJECTION_TYPE,
            "schema_version": EVALUATION_REGISTRY_SCHEMA_VERSION,
            "builder_name": "EvaluationRegistryProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_REGISTRY_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": EVALUATION_SUMMARY_PROJECTION_TYPE,
            "schema_version": EVALUATION_SUMMARY_SCHEMA_VERSION,
            "builder_name": "EvaluationSummaryProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_SUMMARY_PROJECTION_TYPE,
                "reconstruction_source": "evaluation_records",
                "rebuildable": True,
                "authoritative_source": "runtime_evaluation_records",
            },
        },
        {
            "projection_type": EVALUATION_TREND_PROJECTION_TYPE,
            "schema_version": EVALUATION_TREND_SCHEMA_VERSION,
            "builder_name": "EvaluationTrendProjectionBuilderService",
            "reconstruction": {
                "projection_type": EVALUATION_TREND_PROJECTION_TYPE,
                "reconstruction_source": "evaluation_records",
                "rebuildable": True,
                "authoritative_source": "runtime_evaluation_records",
            },
        },
        {
            "projection_type": GOVERNANCE_AUDIT_PROJECTION_TYPE,
            "schema_version": GOVERNANCE_AUDIT_SCHEMA_VERSION,
            "builder_name": "GovernanceAuditProjectionBuilder",
            "reconstruction": {
                "projection_type": GOVERNANCE_AUDIT_PROJECTION_TYPE,
                "reconstruction_source": "runtime_event_store",
                "rebuildable": True,
                "authoritative_source": "runtime_event_store",
            },
        },
        {
            "projection_type": GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
            "schema_version": GOVERNANCE_HEALTH_ROLLUP_SCHEMA_VERSION,
            "builder_name": "GovernanceHealthRollupProjectionBuilderService",
            "reconstruction": {
                "projection_type": GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
                "reconstruction_source": (
                    "evaluation_records,"
                    "recommendation_outcome_projection,"
                    "decision_effectiveness_projection,"
                    "policy_evaluation_overview_projection"
                ),
                "rebuildable": True,
                "authoritative_source": (
                    "runtime_evaluation_records,"
                    "planner_recommendations,"
                    "decision_records,"
                    "policies"
                ),
            },
        },
        {
            "projection_type": POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
            "schema_version": POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION,
            "builder_name": "PolicyEvaluationOverviewProjectionBuilderService",
            "reconstruction": {
                "projection_type": POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
                "reconstruction_source": "policy_evaluation_records",
                "rebuildable": True,
                "authoritative_source": (
                    "policies/policy_decisions/policy_violations/"
                    "runtime_evaluation_records"
                ),
            },
        },
        {
            "projection_type": POLICY_EVIDENCE_PROJECTION_TYPE,
            "schema_version": POLICY_EVIDENCE_SCHEMA_VERSION,
            "builder_name": "PolicyEvidenceProjectionBuilderService",
            "reconstruction": {
                "projection_type": POLICY_EVIDENCE_PROJECTION_TYPE,
                "reconstruction_source": "policy_state",
                "rebuildable": True,
                "authoritative_source": (
                    "policies/policy_decisions/policy_violations/evaluations"
                ),
            },
        },
        {
            "projection_type": POLICY_SUMMARY_PROJECTION_TYPE,
            "schema_version": POLICY_SUMMARY_SCHEMA_VERSION,
            "builder_name": "PolicyProjectionBuilderService",
            "reconstruction": {
                "projection_type": POLICY_SUMMARY_PROJECTION_TYPE,
                "reconstruction_source": "policy_state",
                "rebuildable": True,
                "authoritative_source": (
                    "policies/policy_versions/policy_decisions/"
                    "policy_violations"
                ),
            },
        },
        {
            "projection_type": RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
            "schema_version": RECOMMENDATION_OUTCOME_SCHEMA_VERSION,
            "builder_name": "RecommendationOutcomeProjectionBuilderService",
            "reconstruction": {
                "projection_type": RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
                "reconstruction_source": (
                    "planner_recommendations,"
                    "recommendation_selection_records,"
                    "evaluation_records"
                ),
                "rebuildable": True,
                "authoritative_source": (
                    "planner_recommendations,"
                    "decision_records,"
                    "runtime_evaluation_records"
                ),
            },
        },
        session_agent_execution_projection_builder_service.schema_info.model_dump(),
        {
            "projection_type": SESSION_DECISION_PROJECTION_TYPE,
            "schema_version": SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
            "builder_name": "SessionDecisionProjectionBuilderService",
            "reconstruction": {
                "projection_type": SESSION_DECISION_PROJECTION_TYPE,
                "reconstruction_source": "decision_projection",
                "rebuildable": True,
                "authoritative_source": "runtime_session",
            },
        },
    ]
    assert projection_registry.get_schema(
        DECISION_PROJECTION_TYPE
    ) is not decision_projection_builder_service.schema_info


def test_runtime_projection_endpoint_lists_types_without_building(
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("projection diagnostics must not build projections")

    monkeypatch.setattr(decision_projection_builder_service, "build", fail)
    monkeypatch.setattr(
        session_decision_projection_builder_service,
        "build",
        fail,
    )

    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert response.json() == {
        "projection_types": [
            ARTIFACT_LINEAGE_PROJECTION_TYPE,
            DECISION_EFFECTIVENESS_PROJECTION_TYPE,
            DECISION_LINEAGE_PROJECTION_TYPE,
            DECISION_PROJECTION_TYPE,
            EVALUATION_COVERAGE_PROJECTION_TYPE,
            EVALUATION_DRIFT_PROJECTION_TYPE,
            EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
            EVALUATION_LINEAGE_PROJECTION_TYPE,
            EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
            EVALUATION_REGISTRY_PROJECTION_TYPE,
            EVALUATION_SUMMARY_PROJECTION_TYPE,
            EVALUATION_TREND_PROJECTION_TYPE,
            GOVERNANCE_AUDIT_PROJECTION_TYPE,
            GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
            POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
            POLICY_EVIDENCE_PROJECTION_TYPE,
            POLICY_SUMMARY_PROJECTION_TYPE,
            RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
            SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ],
        "schemas": [
            {
                "projection_type": ARTIFACT_LINEAGE_PROJECTION_TYPE,
                "schema_version": ARTIFACT_LINEAGE_SCHEMA_VERSION,
                "builder_name": "ArtifactLineageProjectionBuilder",
                "reconstruction": {
                    "projection_type": ARTIFACT_LINEAGE_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": DECISION_EFFECTIVENESS_PROJECTION_TYPE,
                "schema_version": DECISION_EFFECTIVENESS_SCHEMA_VERSION,
                "builder_name": "DecisionEffectivenessProjectionBuilderService",
                "reconstruction": {
                    "projection_type": DECISION_EFFECTIVENESS_PROJECTION_TYPE,
                    "reconstruction_source": (
                        "decision_records,evaluation_records"
                    ),
                    "rebuildable": True,
                    "authoritative_source": (
                        "decision_records,runtime_evaluation_records"
                    ),
                },
            },
            {
                "projection_type": DECISION_LINEAGE_PROJECTION_TYPE,
                "schema_version": DECISION_LINEAGE_SCHEMA_VERSION,
                "builder_name": "DecisionLineageProjectionBuilder",
                "reconstruction": {
                    "projection_type": DECISION_LINEAGE_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": DECISION_PROJECTION_TYPE,
                "schema_version": DECISION_PROJECTION_SCHEMA_VERSION,
                "builder_name": "DecisionProjectionBuilderService",
                "reconstruction": {
                    "projection_type": DECISION_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_session_state",
                    "rebuildable": True,
                    "authoritative_source": "runtime_session",
                },
            },
            {
                "projection_type": EVALUATION_COVERAGE_PROJECTION_TYPE,
                "schema_version": EVALUATION_COVERAGE_SCHEMA_VERSION,
                "builder_name": "EvaluationCoverageProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_COVERAGE_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": EVALUATION_DRIFT_PROJECTION_TYPE,
                "schema_version": EVALUATION_DRIFT_SCHEMA_VERSION,
                "builder_name": "EvaluationDriftProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_DRIFT_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": (
                    EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
                ),
                "schema_version": (
                    EVALUATION_INTELLIGENCE_OVERVIEW_SCHEMA_VERSION
                ),
                "builder_name": (
                    "EvaluationIntelligenceOverviewProjectionBuilderService"
                ),
                "reconstruction": {
                    "projection_type": (
                        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
                    ),
                    "reconstruction_source": (
                        "evaluation_registry,evaluation_lineage,"
                        "evaluation_coverage,evaluation_drift"
                    ),
                    "rebuildable": True,
                    "authoritative_source": (
                        "evaluation_registry,evaluation_lineage,"
                        "evaluation_coverage,evaluation_drift"
                    ),
                },
            },
            {
                "projection_type": EVALUATION_LINEAGE_PROJECTION_TYPE,
                "schema_version": EVALUATION_LINEAGE_SCHEMA_VERSION,
                "builder_name": "EvaluationLineageProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_LINEAGE_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
                "schema_version": EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION,
                "builder_name": "EvaluationOutcomeRollupProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
                    "reconstruction_source": "evaluation_records",
                    "rebuildable": True,
                    "authoritative_source": "runtime_evaluation_records",
                },
            },
            {
                "projection_type": EVALUATION_REGISTRY_PROJECTION_TYPE,
                "schema_version": EVALUATION_REGISTRY_SCHEMA_VERSION,
                "builder_name": "EvaluationRegistryProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_REGISTRY_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": EVALUATION_SUMMARY_PROJECTION_TYPE,
                "schema_version": EVALUATION_SUMMARY_SCHEMA_VERSION,
                "builder_name": "EvaluationSummaryProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_SUMMARY_PROJECTION_TYPE,
                    "reconstruction_source": "evaluation_records",
                    "rebuildable": True,
                    "authoritative_source": "runtime_evaluation_records",
                },
            },
            {
                "projection_type": EVALUATION_TREND_PROJECTION_TYPE,
                "schema_version": EVALUATION_TREND_SCHEMA_VERSION,
                "builder_name": "EvaluationTrendProjectionBuilderService",
                "reconstruction": {
                    "projection_type": EVALUATION_TREND_PROJECTION_TYPE,
                    "reconstruction_source": "evaluation_records",
                    "rebuildable": True,
                    "authoritative_source": "runtime_evaluation_records",
                },
            },
            {
                "projection_type": GOVERNANCE_AUDIT_PROJECTION_TYPE,
                "schema_version": GOVERNANCE_AUDIT_SCHEMA_VERSION,
                "builder_name": "GovernanceAuditProjectionBuilder",
                "reconstruction": {
                    "projection_type": GOVERNANCE_AUDIT_PROJECTION_TYPE,
                    "reconstruction_source": "runtime_event_store",
                    "rebuildable": True,
                    "authoritative_source": "runtime_event_store",
                },
            },
            {
                "projection_type": GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
                "schema_version": GOVERNANCE_HEALTH_ROLLUP_SCHEMA_VERSION,
                "builder_name": (
                    "GovernanceHealthRollupProjectionBuilderService"
                ),
                "reconstruction": {
                    "projection_type": GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
                    "reconstruction_source": (
                        "evaluation_records,"
                        "recommendation_outcome_projection,"
                        "decision_effectiveness_projection,"
                        "policy_evaluation_overview_projection"
                    ),
                    "rebuildable": True,
                    "authoritative_source": (
                        "runtime_evaluation_records,"
                        "planner_recommendations,"
                        "decision_records,"
                        "policies"
                    ),
                },
            },
            {
                "projection_type": POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
                "schema_version": POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION,
                "builder_name": "PolicyEvaluationOverviewProjectionBuilderService",
                "reconstruction": {
                    "projection_type": POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
                    "reconstruction_source": "policy_evaluation_records",
                    "rebuildable": True,
                    "authoritative_source": (
                        "policies/policy_decisions/policy_violations/"
                        "runtime_evaluation_records"
                    ),
                },
            },
            {
                "projection_type": POLICY_EVIDENCE_PROJECTION_TYPE,
                "schema_version": POLICY_EVIDENCE_SCHEMA_VERSION,
                "builder_name": "PolicyEvidenceProjectionBuilderService",
                "reconstruction": {
                    "projection_type": POLICY_EVIDENCE_PROJECTION_TYPE,
                    "reconstruction_source": "policy_state",
                    "rebuildable": True,
                    "authoritative_source": (
                        "policies/policy_decisions/policy_violations/evaluations"
                    ),
                },
            },
            {
                "projection_type": POLICY_SUMMARY_PROJECTION_TYPE,
                "schema_version": POLICY_SUMMARY_SCHEMA_VERSION,
                "builder_name": "PolicyProjectionBuilderService",
                "reconstruction": {
                    "projection_type": POLICY_SUMMARY_PROJECTION_TYPE,
                    "reconstruction_source": "policy_state",
                    "rebuildable": True,
                    "authoritative_source": (
                        "policies/policy_versions/policy_decisions/"
                        "policy_violations"
                    ),
                },
            },
            {
                "projection_type": RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
                "schema_version": RECOMMENDATION_OUTCOME_SCHEMA_VERSION,
                "builder_name": (
                    "RecommendationOutcomeProjectionBuilderService"
                ),
                "reconstruction": {
                    "projection_type": RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
                    "reconstruction_source": (
                        "planner_recommendations,"
                        "recommendation_selection_records,"
                        "evaluation_records"
                    ),
                    "rebuildable": True,
                    "authoritative_source": (
                        "planner_recommendations,"
                        "decision_records,"
                        "runtime_evaluation_records"
                    ),
                },
            },
            session_agent_execution_projection_builder_service.schema_info.model_dump(),
            {
                "projection_type": SESSION_DECISION_PROJECTION_TYPE,
                "schema_version": SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
                "builder_name": "SessionDecisionProjectionBuilderService",
                "reconstruction": {
                    "projection_type": SESSION_DECISION_PROJECTION_TYPE,
                    "reconstruction_source": "decision_projection",
                    "rebuildable": True,
                    "authoritative_source": "runtime_session",
                },
            },
        ],
        "projections": [
            {
                "projection_name": ARTIFACT_LINEAGE_PROJECTION_TYPE,
                "projection_version": ARTIFACT_LINEAGE_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": DECISION_EFFECTIVENESS_PROJECTION_TYPE,
                "projection_version": DECISION_EFFECTIVENESS_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": DECISION_LINEAGE_PROJECTION_TYPE,
                "projection_version": DECISION_LINEAGE_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": DECISION_PROJECTION_TYPE,
                "projection_version": DECISION_PROJECTION_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_COVERAGE_PROJECTION_TYPE,
                "projection_version": EVALUATION_COVERAGE_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_DRIFT_PROJECTION_TYPE,
                "projection_version": EVALUATION_DRIFT_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": (
                    EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
                ),
                "projection_version": (
                    EVALUATION_INTELLIGENCE_OVERVIEW_SCHEMA_VERSION
                ),
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_LINEAGE_PROJECTION_TYPE,
                "projection_version": EVALUATION_LINEAGE_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
                "projection_version": EVALUATION_OUTCOME_ROLLUP_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_REGISTRY_PROJECTION_TYPE,
                "projection_version": EVALUATION_REGISTRY_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_SUMMARY_PROJECTION_TYPE,
                "projection_version": EVALUATION_SUMMARY_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": EVALUATION_TREND_PROJECTION_TYPE,
                "projection_version": EVALUATION_TREND_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": GOVERNANCE_AUDIT_PROJECTION_TYPE,
                "projection_version": GOVERNANCE_AUDIT_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
                "projection_version": GOVERNANCE_HEALTH_ROLLUP_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
                "projection_version": POLICY_EVALUATION_OVERVIEW_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": POLICY_EVIDENCE_PROJECTION_TYPE,
                "projection_version": POLICY_EVIDENCE_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": POLICY_SUMMARY_PROJECTION_TYPE,
                "projection_version": POLICY_SUMMARY_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
                "projection_version": RECOMMENDATION_OUTCOME_SCHEMA_VERSION,
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
                "projection_version": (
                    SESSION_AGENT_EXECUTION_PROJECTION_SCHEMA_VERSION
                ),
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
            {
                "projection_name": SESSION_DECISION_PROJECTION_TYPE,
                "projection_version": (
                    SESSION_DECISION_PROJECTION_SCHEMA_VERSION
                ),
                "latest_rebuild_status": None,
                "latest_rebuild_started_at": None,
                "latest_rebuild_completed_at": None,
                "latest_rebuild_duration_ms": None,
            },
        ],
    }
    events = event_service.list_persisted_events(
        event_type="projection_registry_inspected"
    )
    assert len(events) == 1
    assert events[0].metadata == {
        "projection_type_count": 20,
        "projection_types": [
            ARTIFACT_LINEAGE_PROJECTION_TYPE,
            DECISION_EFFECTIVENESS_PROJECTION_TYPE,
            DECISION_LINEAGE_PROJECTION_TYPE,
            DECISION_PROJECTION_TYPE,
            EVALUATION_COVERAGE_PROJECTION_TYPE,
            EVALUATION_DRIFT_PROJECTION_TYPE,
            EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
            EVALUATION_LINEAGE_PROJECTION_TYPE,
            EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
            EVALUATION_REGISTRY_PROJECTION_TYPE,
            EVALUATION_SUMMARY_PROJECTION_TYPE,
            EVALUATION_TREND_PROJECTION_TYPE,
            GOVERNANCE_AUDIT_PROJECTION_TYPE,
            GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
            POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
            POLICY_EVIDENCE_PROJECTION_TYPE,
            POLICY_SUMMARY_PROJECTION_TYPE,
            RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
            SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ],
        "source": "projection_registry",
    }


def test_runtime_projection_endpoint_does_not_expose_payloads() -> None:
    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    assert set(response.json()) == {
        "projection_types",
        "schemas",
        "projections",
    }
    response_text = response.text
    for excluded_field in (
        "metadata",
        "decision_id",
        "recommendation_id",
        "session_id",
    ):
        assert excluded_field not in response_text


@pytest.mark.parametrize(
    (
        "projection_type",
        "schema_version",
        "builder_name",
        "reconstruction_source",
        "authoritative_source",
    ),
    [
        (
            DECISION_PROJECTION_TYPE,
            DECISION_PROJECTION_SCHEMA_VERSION,
            "DecisionProjectionBuilderService",
            "runtime_session_state",
            "runtime_session",
        ),
        (
            SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
            SESSION_AGENT_EXECUTION_PROJECTION_SCHEMA_VERSION,
            "SessionAgentExecutionProjectionBuilderService",
            "runtime_event_store",
            "runtime_event_store",
        ),
        (
            SESSION_DECISION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
            "SessionDecisionProjectionBuilderService",
            "decision_projection",
            "runtime_session",
        ),
    ],
)
def test_runtime_projection_type_detail_returns_discovery_metadata(
    projection_type: str,
    schema_version: int,
    builder_name: str,
    reconstruction_source: str,
    authoritative_source: str,
) -> None:
    response = TestClient(app).get(
        f"/runtime/projections/{projection_type}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "projection_type": projection_type,
        "schema_version": schema_version,
        "registered": True,
        "builder_name": builder_name,
        "reconstruction": {
            "projection_type": projection_type,
            "reconstruction_source": reconstruction_source,
            "rebuildable": True,
            "authoritative_source": authoritative_source,
        },
        "source": "projection_registry",
    }


def test_runtime_projection_type_detail_returns_standard_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/projections/missing_projection"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }


def test_runtime_projection_type_detail_does_not_build_or_expose_payloads(
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("projection discovery must not build projections")

    monkeypatch.setattr(decision_projection_builder_service, "build", fail)

    response = TestClient(app).get(
        f"/runtime/projections/{DECISION_PROJECTION_TYPE}"
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "projection_type",
        "schema_version",
        "registered",
        "builder_name",
        "reconstruction",
        "source",
    }
    response_text = response.text
    for excluded_field in (
        "metadata",
        "decision_id",
        "recommendation_id",
        "session_id",
        "planning_context",
        "cognitive_state",
        "projections",
    ):
        assert excluded_field not in response_text


def test_runtime_projection_list_retains_existing_discovery_fields() -> None:
    response = TestClient(app).get("/runtime/projections")

    assert response.status_code == 200
    body = response.json()
    assert {
        "projection_types": body["projection_types"],
        "schemas": body["schemas"],
    } == {
        "projection_types": [
            ARTIFACT_LINEAGE_PROJECTION_TYPE,
            DECISION_EFFECTIVENESS_PROJECTION_TYPE,
            DECISION_LINEAGE_PROJECTION_TYPE,
            DECISION_PROJECTION_TYPE,
            EVALUATION_COVERAGE_PROJECTION_TYPE,
            EVALUATION_DRIFT_PROJECTION_TYPE,
            EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
            EVALUATION_LINEAGE_PROJECTION_TYPE,
            EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
            EVALUATION_REGISTRY_PROJECTION_TYPE,
            EVALUATION_SUMMARY_PROJECTION_TYPE,
            EVALUATION_TREND_PROJECTION_TYPE,
            GOVERNANCE_AUDIT_PROJECTION_TYPE,
            GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
            POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
            POLICY_EVIDENCE_PROJECTION_TYPE,
            POLICY_SUMMARY_PROJECTION_TYPE,
            RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
            SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
            SESSION_DECISION_PROJECTION_TYPE,
        ],
        "schemas": [
            artifact_lineage_projection_builder.schema_info.model_dump(),
            decision_effectiveness_projection_builder_service.schema_info.model_dump(),
            decision_lineage_projection_builder.schema_info.model_dump(),
            decision_projection_builder_service.schema_info.model_dump(),
            evaluation_coverage_projection_builder_service.schema_info.model_dump(),
            evaluation_drift_projection_builder_service.schema_info.model_dump(),
            evaluation_intelligence_overview_projection_builder_service.schema_info.model_dump(),
            evaluation_lineage_projection_builder_service.schema_info.model_dump(),
            evaluation_outcome_rollup_projection_builder_service.schema_info.model_dump(),
            evaluation_registry_projection_builder_service.schema_info.model_dump(),
            evaluation_summary_projection_builder_service.schema_info.model_dump(),
            evaluation_trend_projection_builder_service.schema_info.model_dump(),
            governance_audit_projection_builder.schema_info.model_dump(),
            governance_health_rollup_projection_builder_service.schema_info.model_dump(),
            policy_evaluation_overview_projection_builder_service.schema_info.model_dump(),
            policy_evidence_projection_builder_service.schema_info.model_dump(),
            policy_projection_builder_service.schema_info.model_dump(),
            recommendation_outcome_projection_builder_service.schema_info.model_dump(),
            session_agent_execution_projection_builder_service.schema_info.model_dump(),
            session_decision_projection_builder_service.schema_info.model_dump(),
        ],
    }
