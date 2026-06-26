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
from app.models.projection_replay import ProjectionReplayRequest
from app.runtime.projection_registry import ProjectionRegistry
from app.services.evaluation_coverage_projection_builder_service import (
    EvaluationCoverageProjectionBuilderService,
)
from app.services.evaluation_coverage_service import EvaluationCoverageService
from app.services.evaluation_drift_projection_builder_service import (
    EvaluationDriftProjectionBuilderService,
)
from app.services.evaluation_drift_service import EvaluationDriftService
from app.services.evaluation_intelligence_overview_projection_builder_service import (
    EvaluationIntelligenceOverviewProjectionBuilderService,
)
from app.services.evaluation_intelligence_overview_service import (
    EvaluationIntelligenceOverviewService,
)
from app.services.evaluation_lineage_projection_builder_service import (
    EvaluationLineageProjectionBuilderService,
)
from app.services.evaluation_lineage_service import EvaluationLineageService
from app.services.evaluation_reconstruction_service import (
    EVALUATION_RECONSTRUCTION_PROJECTIONS,
    EVALUATION_RECONSTRUCTION_SOURCE,
    EvaluationReconstructionService,
)
from app.services.evaluation_registry_projection_builder_service import (
    EvaluationRegistryProjectionBuilderService,
)
from app.services.evaluation_registry_service import EvaluationRegistryService
from app.services.event_service import EventService
from app.services.projection_rebuild_service import ProjectionRebuildService
from app.services.projection_replay_service import ProjectionReplayService
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


def make_reconstruction_service(tmp_path) -> EvaluationReconstructionService:
    events = EventService(
        TraceService(tmp_path / "evaluation-reconstruction.db")
    )
    registry_service = EvaluationRegistryService(events=events)
    lineage_service = EvaluationLineageService(events=events)
    coverage_service = EvaluationCoverageService(events=events)
    drift_service = EvaluationDriftService(events=events)

    registry_service.register_definition(
        EvaluationDefinitionCreate(
            evaluation_id="eval-policy",
            name="Policy evaluation",
            description="Policy evaluation definition.",
            category="policy",
            version=1,
            status="active",
        )
    )
    registry_service.register_definition(
        EvaluationDefinitionCreate(
            evaluation_id="eval-runtime",
            name="Runtime evaluation",
            description="Runtime evaluation definition.",
            category="runtime",
            version=1,
            status="active",
        )
    )
    registry_service.register_suite(
        EvaluationSuiteCreate(
            suite_id="suite-evaluation",
            name="Evaluation suite",
            description="Evaluation suite.",
            evaluation_ids=["eval-policy", "eval-runtime"],
        )
    )

    lineage_service.register_lineage(
        EvaluationLineageRecordCreate(
            lineage_id="lineage-policy",
            evaluation_id="eval-policy",
            evaluation_name="Policy evaluation",
            evaluation_version=1,
            source_type="policy",
            source_id="policy-1",
            source_category="governance",
        )
    )
    lineage_service.register_evidence(
        EvaluationEvidenceRecordCreate(
            evidence_id="evidence-policy",
            lineage_id="lineage-policy",
            evidence_type="runtime_record",
            evidence_reference="record-1",
            description="Evidence record.",
        )
    )

    coverage_service.register_target(
        CoverageTargetCreate(
            target_id="target-policy",
            target_name="Policy target",
            target_type="policy",
            target_category="governance",
            description="Policy target.",
        )
    )
    coverage_service.register_target(
        CoverageTargetCreate(
            target_id="target-runtime",
            target_name="Runtime target",
            target_type="runtime_component",
            target_category="runtime",
            description="Runtime target.",
        )
    )
    coverage_service.register_mapping(
        CoverageMappingCreate(
            mapping_id="mapping-policy",
            target_id="target-policy",
            evaluation_id="eval-policy",
            evaluation_name="Policy evaluation",
            evaluation_version=1,
        )
    )

    drift_service.register_baseline(
        EvaluationDriftBaselineCreate(
            baseline_id="baseline-policy",
            evaluation_id="eval-policy",
            evaluation_name="Policy evaluation",
            evaluation_version=1,
            baseline_score=0.8,
            baseline_pass_count=8,
            baseline_fail_count=2,
        )
    )
    drift_service.register_observation(
        EvaluationDriftObservationCreate(
            observation_id="observation-policy",
            evaluation_id="eval-policy",
            evaluation_name="Policy evaluation",
            evaluation_version=1,
            observed_score=0.7,
            observed_pass_count=7,
            observed_fail_count=3,
        )
    )

    registry_builder = EvaluationRegistryProjectionBuilderService(
        registry=registry_service,
        clock=lambda: GENERATED_AT,
    )
    lineage_builder = EvaluationLineageProjectionBuilderService(
        lineage=lineage_service,
        clock=lambda: GENERATED_AT,
    )
    coverage_builder = EvaluationCoverageProjectionBuilderService(
        coverage=coverage_service,
        clock=lambda: GENERATED_AT,
    )
    drift_builder = EvaluationDriftProjectionBuilderService(
        drift=drift_service,
        clock=lambda: GENERATED_AT,
    )
    overview_builder = EvaluationIntelligenceOverviewProjectionBuilderService(
        overview=EvaluationIntelligenceOverviewService(
            registry=registry_builder,
            lineage=lineage_builder,
            coverage=coverage_builder,
            drift=drift_builder,
        ),
        clock=lambda: GENERATED_AT,
    )

    registry = ProjectionRegistry()
    registry.register(coverage_builder)
    registry.register(drift_builder)
    registry.register(overview_builder)
    registry.register(lineage_builder)
    registry.register(registry_builder)

    return EvaluationReconstructionService(
        registry=registry,
        rebuilds=ProjectionRebuildService(registry=registry, events=events),
        replay=ProjectionReplayService(registry=registry, events=events),
    )


def projection_by_name(result):
    return {
        projection.projection_name: projection
        for projection in result.projections
    }


def test_evaluation_reconstruction_inspection_metadata(tmp_path) -> None:
    service = make_reconstruction_service(tmp_path)

    result = service.inspect()

    assert [item.projection_name for item in result.projections] == (
        EVALUATION_RECONSTRUCTION_PROJECTIONS
    )
    assert result.total_projections == 5
    assert result.successful_reconstructions == 0
    assert result.failed_reconstructions == 0
    assert result.replay_validation_status == "not_verified"
    assert all(item.rebuild_supported for item in result.projections)
    assert projection_by_name(result)[
        "evaluation_intelligence_overview"
    ].reconstruction_source == (
        "evaluation_registry,evaluation_lineage,evaluation_coverage,"
        "evaluation_drift"
    )


def test_rebuilds_all_evaluation_projections_deterministically(tmp_path) -> None:
    service = make_reconstruction_service(tmp_path)

    first = service.rebuild_all()
    second = service.rebuild_all()

    assert first.total_projections == 5
    assert first.successful_reconstructions == 5
    assert first.failed_reconstructions == 0
    assert first.replay_validation_status == "verified"
    assert [
        item.model_dump(exclude={"last_reconstruction_time"})
        for item in first.projections
    ] == [
        item.model_dump(exclude={"last_reconstruction_time"})
        for item in second.projections
    ]


def test_individual_projection_reconstruction_counts(tmp_path) -> None:
    service = make_reconstruction_service(tmp_path)

    registry = service.rebuild_projection(
        "evaluation_registry"
    ).projection_data
    lineage = service.rebuild_projection(
        "evaluation_lineage"
    ).projection_data
    coverage = service.rebuild_projection(
        "evaluation_coverage"
    ).projection_data
    drift = service.rebuild_projection("evaluation_drift").projection_data
    overview = service.rebuild_projection(
        "evaluation_intelligence_overview"
    ).projection_data

    assert registry.total_definitions == 2
    assert registry.total_suites == 1
    assert lineage.total_lineage_records == 1
    assert lineage.total_evidence_records == 1
    assert coverage.total_targets == 2
    assert len(coverage.covered_targets) == 1
    assert len(coverage.uncovered_targets) == 1
    assert drift.total_drift_records == 1
    assert drift.regressed_count == 1
    assert overview.total_evaluations == 2
    assert overview.regressing_evaluations == 1
    assert overview.healthy_evaluations == 1


def test_runtime_replay_recognizes_evaluation_projections(tmp_path) -> None:
    service = make_reconstruction_service(tmp_path)

    for projection_name in EVALUATION_RECONSTRUCTION_PROJECTIONS:
        replay = service._replay.preview(
            ProjectionReplayRequest(projection_name=projection_name)
        )
        assert replay.projection_name == projection_name
        assert replay.status == "completed"
        assert replay.dry_run is True


def test_evaluation_reconstruction_routes_work() -> None:
    client = TestClient(app)

    inspect_response = client.get("/evaluation-reconstruction")
    rebuild_response = client.post("/evaluation-reconstruction/rebuild")

    assert inspect_response.status_code == 200
    assert rebuild_response.status_code == 200
    assert inspect_response.json()["total_projections"] == 5
    assert rebuild_response.json()["total_projections"] == 5
    assert rebuild_response.json()["replay_validation_status"] == "verified"


def test_diagnostics_and_projection_metadata_expose_reconstruction() -> None:
    client = TestClient(app)

    diagnostics = client.get("/evaluation-diagnostics")
    projections = client.get("/runtime/projection-diagnostics")

    assert diagnostics.status_code == 200
    assert projections.status_code == 200
    projection_by_type = {
        projection["projection_name"]: projection
        for projection in diagnostics.json()["projections"]
    }
    for projection_name in EVALUATION_RECONSTRUCTION_PROJECTIONS:
        assert projection_by_type[projection_name]["rebuild_supported"] is True
        assert projection_by_type[projection_name]["reconstruction_status"] == (
            "supported"
        )
        assert projection_by_type[projection_name]["replay_verified"] is False
        assert projection_name in projections.json()["projection_types"]


def test_runtime_diagnostics_include_evaluation_reconstruction(monkeypatch) -> None:
    from app.services.diagnostics_service import DiagnosticsService

    service = DiagnosticsService()
    monkeypatch.setattr(
        service,
        "event_store_health",
        lambda: {
            "total_events": 0,
            "latest_event_timestamp": None,
            "latest_event_type": None,
            "missing_task_id_count": 0,
        },
    )
    monkeypatch.setattr(
        service,
        "_task_health",
        lambda: {
            "total_tasks": 0,
            "status_counts": {
                "created": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
            },
        },
    )
    monkeypatch.setattr(
        service,
        "proposal_health",
        lambda: {
            "total_proposals": 0,
            "status_counts": {
                "proposed": 0,
                "approved": 0,
                "rejected": 0,
            },
            "source_type_counts": {},
            "unresolved_count": 0,
            "missing_proposal_id_count": 0,
        },
    )
    monkeypatch.setattr(
        service,
        "planner_recommendation_health",
        lambda: {
            "total_recommendations": 0,
            "planner_recommendation_status_counts": {
                "active": 0,
                "promoted": 0,
                "dismissed": 0,
            },
        },
    )
    monkeypatch.setattr(
        service,
        "decision_record_health",
        lambda: {"decision_record_count": 0},
    )
    monkeypatch.setattr(
        service,
        "decision_evidence_health",
        lambda: {"decision_evidence_count": 0},
    )
    monkeypatch.setattr(
        service,
        "decision_trail_health",
        lambda: {"proposals_with_decision_trails": 0},
    )
    monkeypatch.setattr(
        service,
        "governance_health",
        lambda: {
            "severity_counts": {},
            "highest_severity": None,
            "has_critical": False,
            "status": "ok",
            "error_budget": {"status": "within_budget"},
        },
    )
    monkeypatch.setattr(
        service._reconstruction,
        "task_consistency_health",
        lambda: {"inconsistent": False},
    )
    monkeypatch.setattr(
        service._reconstruction,
        "proposal_consistency_health",
        lambda: {"inconsistent": False},
    )

    summary = service.runtime_summary()

    assert summary["evaluation_reconstruction"] == {
        "projections_rebuildable": 5,
        "successful_reconstructions": 0,
        "failed_reconstructions": 0,
        "replay_validation_status": "not_verified",
    }
