from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_coverage import (
    CoverageMappingCreate,
    CoverageTargetCreate,
)
from app.models.evaluation_drift import (
    EvaluationDriftBaselineCreate,
    EvaluationDriftObservationCreate,
)
from app.models.evaluation_lineage import (
    EvaluationEvidenceRecordCreate,
    EvaluationLineageRecordCreate,
)
from app.models.evaluation_registry import (
    EvaluationDefinitionCreate,
    EvaluationSuiteCreate,
)
from app.models.query_executor import QueryExecutionRequest
from app.services.evaluation_coverage_projection_builder_service import (
    EvaluationCoverageProjectionBuilderService,
)
from app.services.evaluation_coverage_service import EvaluationCoverageService
from app.services.evaluation_drift_projection_builder_service import (
    EvaluationDriftProjectionBuilderService,
)
from app.services.evaluation_drift_service import EvaluationDriftService
from app.services.evaluation_intelligence_overview_projection_builder_service import (
    EVALUATION_INTELLIGENCE_OVERVIEW_DEPENDENCIES,
    EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
    EvaluationIntelligenceOverviewProjectionBuilderService,
)
from app.services.evaluation_intelligence_overview_service import (
    EvaluationIntelligenceOverviewService,
)
from app.services.evaluation_lineage_projection_builder_service import (
    EvaluationLineageProjectionBuilderService,
)
from app.services.evaluation_lineage_service import EvaluationLineageService
from app.services.evaluation_registry_projection_builder_service import (
    EvaluationRegistryProjectionBuilderService,
)
from app.services.evaluation_registry_service import EvaluationRegistryService
from app.services.event_service import EventService
from app.services.query_executor_service import query_executor_service
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


def make_builder(tmp_path) -> EvaluationIntelligenceOverviewProjectionBuilderService:
    events = EventService(
        TraceService(tmp_path / "evaluation-intelligence-overview.db")
    )
    registry = EvaluationRegistryService(events=events)
    lineage = EvaluationLineageService(events=events)
    coverage = EvaluationCoverageService(events=events)
    drift = EvaluationDriftService(events=events)

    registry.register_definition(
        EvaluationDefinitionCreate(
            evaluation_id="eval-policy-quality",
            name="Policy quality",
            description="Checks policy quality.",
            category="policy",
            version=1,
            status="active",
        )
    )
    registry.register_definition(
        EvaluationDefinitionCreate(
            evaluation_id="eval-runtime-safety",
            name="Runtime safety",
            description="Checks runtime safety.",
            category="runtime",
            version=1,
            status="active",
        )
    )
    registry.register_suite(
        EvaluationSuiteCreate(
            suite_id="suite-governance",
            name="Governance suite",
            description="Governance evaluation suite.",
            evaluation_ids=[
                "eval-policy-quality",
                "eval-runtime-safety",
            ],
        )
    )

    lineage.register_lineage(
        EvaluationLineageRecordCreate(
            lineage_id="lineage-policy-quality",
            evaluation_id="eval-policy-quality",
            evaluation_name="Policy quality",
            evaluation_version=1,
            source_type="policy",
            source_id="policy-1",
            source_category="governance",
        )
    )
    lineage.register_evidence(
        EvaluationEvidenceRecordCreate(
            evidence_id="evidence-policy-quality",
            lineage_id="lineage-policy-quality",
            evidence_type="runtime_record",
            evidence_reference="record-1",
            description="Runtime evidence.",
        )
    )

    coverage.register_target(
        CoverageTargetCreate(
            target_id="target-policy",
            target_name="Policy surface",
            target_type="policy",
            target_category="governance",
            description="Policy evaluation target.",
        )
    )
    coverage.register_target(
        CoverageTargetCreate(
            target_id="target-provider",
            target_name="Provider surface",
            target_type="runtime_component",
            target_category="runtime",
            description="Provider evaluation target.",
        )
    )
    coverage.register_mapping(
        CoverageMappingCreate(
            mapping_id="mapping-policy",
            target_id="target-policy",
            evaluation_id="eval-policy-quality",
            evaluation_name="Policy quality",
            evaluation_version=1,
        )
    )

    drift.register_baseline(
        EvaluationDriftBaselineCreate(
            baseline_id="baseline-policy",
            evaluation_id="eval-policy-quality",
            evaluation_name="Policy quality",
            evaluation_version=1,
            baseline_score=0.8,
            baseline_pass_count=8,
            baseline_fail_count=2,
        )
    )
    drift.register_observation(
        EvaluationDriftObservationCreate(
            observation_id="observation-policy-regressed",
            evaluation_id="eval-policy-quality",
            evaluation_name="Policy quality",
            evaluation_version=1,
            observed_score=0.7,
            observed_pass_count=7,
            observed_fail_count=3,
        )
    )
    drift.register_observation(
        EvaluationDriftObservationCreate(
            observation_id="observation-policy-unchanged",
            evaluation_id="eval-policy-quality",
            evaluation_name="Policy quality",
            evaluation_version=1,
            observed_score=0.8,
            observed_pass_count=8,
            observed_fail_count=2,
        )
    )
    drift.register_baseline(
        EvaluationDriftBaselineCreate(
            baseline_id="baseline-runtime",
            evaluation_id="eval-runtime-safety",
            evaluation_name="Runtime safety",
            evaluation_version=1,
            baseline_score=0.6,
            baseline_pass_count=6,
            baseline_fail_count=4,
        )
    )
    drift.register_observation(
        EvaluationDriftObservationCreate(
            observation_id="observation-runtime-improved",
            evaluation_id="eval-runtime-safety",
            evaluation_name="Runtime safety",
            evaluation_version=1,
            observed_score=0.9,
            observed_pass_count=9,
            observed_fail_count=1,
        )
    )

    overview = EvaluationIntelligenceOverviewService(
        registry=EvaluationRegistryProjectionBuilderService(
            registry=registry,
            clock=lambda: GENERATED_AT,
        ),
        lineage=EvaluationLineageProjectionBuilderService(
            lineage=lineage,
            clock=lambda: GENERATED_AT,
        ),
        coverage=EvaluationCoverageProjectionBuilderService(
            coverage=coverage,
            clock=lambda: GENERATED_AT,
        ),
        drift=EvaluationDriftProjectionBuilderService(
            drift=drift,
            clock=lambda: GENERATED_AT,
        ),
    )
    return EvaluationIntelligenceOverviewProjectionBuilderService(
        overview=overview,
        clock=lambda: GENERATED_AT,
    )


def test_overview_aggregates_registry_lineage_coverage_and_drift(
    tmp_path,
) -> None:
    projection = make_builder(tmp_path).build()

    assert projection.total_evaluations == 2
    assert projection.total_suites == 1
    assert projection.total_coverage_targets == 2
    assert projection.covered_targets == 1
    assert projection.uncovered_targets == 1
    assert projection.coverage_percentage == 50.0
    assert projection.total_lineage_records == 1
    assert projection.total_evidence_records == 1
    assert projection.total_drift_records == 3
    assert projection.regressed_count == 1
    assert projection.improved_count == 1
    assert projection.unchanged_count == 1


def test_healthy_and_regressing_evaluation_counts_are_unique(tmp_path) -> None:
    projection = make_builder(tmp_path).build()

    assert projection.regressing_evaluations == 1
    assert projection.healthy_evaluations == 1


def test_overview_rebuild_is_deterministic_and_dependency_metadata_visible(
    tmp_path,
) -> None:
    builder = make_builder(tmp_path)

    first = builder.build().model_dump(mode="json")
    second = builder.build().model_dump(mode="json")

    assert first == second
    assert first["metadata"]["projection_type"] == (
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
    )
    assert first["metadata"]["builder_name"] == (
        "EvaluationIntelligenceOverviewProjectionBuilderService"
    )
    assert first["metadata"]["reconstruction"] == {
        "projection_type": EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE,
        "reconstruction_source": EVALUATION_INTELLIGENCE_OVERVIEW_DEPENDENCIES,
        "rebuildable": True,
        "authoritative_source": EVALUATION_INTELLIGENCE_OVERVIEW_DEPENDENCIES,
    }


def test_overview_routes_work() -> None:
    client = TestClient(app)

    overview = client.get("/evaluation-intelligence-overview")
    projection = client.get("/evaluation-intelligence-overview/projection")

    assert overview.status_code == 200
    assert projection.status_code == 200
    assert overview.json()["metadata"]["projection_type"] == (
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
    )
    assert projection.json()["metadata"]["projection_type"] == (
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
    )


def test_projection_registry_diagnostics_and_query_executor_visibility() -> None:
    client = TestClient(app)

    runtime_response = client.get("/runtime/projections")
    diagnostics_response = client.get("/runtime/projection-diagnostics")
    contract_response = client.get(
        "/runtime/projections/registry/evaluation_intelligence_overview"
    )
    query_response = client.post(
        "/runtime/query-execute",
        json={"query_id": "evaluation_intelligence_overview"},
    )
    direct_query = query_executor_service.execute(
        QueryExecutionRequest(
            query_id="runtime.evaluation_intelligence_overview"
        )
    )

    assert runtime_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert contract_response.status_code == 200
    assert query_response.status_code == 200
    assert EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE in (
        runtime_response.json()["projection_types"]
    )
    assert EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE in (
        diagnostics_response.json()["projection_types"]
    )
    assert contract_response.json()["projection_name"] == (
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
    )
    assert contract_response.json()["route"] == (
        "/evaluation-intelligence-overview/projection"
    )
    assert contract_response.json()["capabilities"]["reconstructable"] is True
    assert query_response.json()["projection_type"] == (
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
    )
    assert direct_query.projection_type == (
        EVALUATION_INTELLIGENCE_OVERVIEW_PROJECTION_TYPE
    )
