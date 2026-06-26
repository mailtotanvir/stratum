from fastapi.testclient import TestClient

from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.artifact_service import ArtifactService
from app.services.evaluation_diagnostics_service import (
    evaluation_diagnostics_service,
)
from app.services.evaluation_service import EvaluationService
from app.services.diagnostics_service import DiagnosticsService
from app.services.runtime_session_service import RuntimeSessionService


EXPECTED_EVALUATION_PROJECTIONS = [
    "evaluation_coverage",
    "evaluation_drift",
    "evaluation_intelligence_overview",
    "evaluation_lineage",
    "evaluation_outcome_rollup",
    "evaluation_registry",
    "evaluation_summary",
    "evaluation_trend",
]


def make_fixture(tmp_path):
    artifacts = ArtifactService(tmp_path / "artifacts.db")
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    evaluations = EvaluationService(
        tmp_path / "evaluations.db",
        artifacts=artifacts,
        sessions=sessions,
    )
    return evaluations, artifacts, sessions


def test_diagnostics_returns_evaluation_counts(tmp_path) -> None:
    evaluations, artifacts, sessions = make_fixture(tmp_path)
    session = sessions.create_session("task-diagnostics")
    artifact = artifacts.create_artifact_without_event(
        path="reports/diagnostics.md",
        kind="report",
        task_id=session.task_id,
    )
    quality = evaluations.create_dimension("Quality", "Signal")
    safety = evaluations.create_dimension("Safety", "Signal")
    first = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="recorded",
    )
    second = evaluations.create_evaluation(
        session_id="missing-session",
        evaluation_type="manual_review",
        status="draft",
    )
    evaluations.add_result(first.id, quality.id, 2.0, "Quality")
    evaluations.add_result(first.id, safety.id, 4.0, "Safety")

    service = type(evaluation_diagnostics_service)(
        evaluations=evaluations
    )
    diagnostics = service.generate()

    assert diagnostics.evaluation_count == 2
    assert diagnostics.result_count == 2
    assert diagnostics.dimension_count == 2
    assert diagnostics.target_snapshot_count == 1
    assert diagnostics.evaluations_without_results_count == 1
    assert diagnostics.evaluations_without_target_snapshot_count == 1


def test_diagnostics_lists_registered_evaluation_projections(tmp_path) -> None:
    evaluations, _, _ = make_fixture(tmp_path)
    service = type(evaluation_diagnostics_service)(
        evaluations=evaluations
    )

    diagnostics = service.generate()

    assert diagnostics.registered_projection_types == (
        EXPECTED_EVALUATION_PROJECTIONS
    )
    assert diagnostics.total_projections == 8
    assert diagnostics.healthy_projections == 8
    assert diagnostics.unhealthy_projections == 0
    assert diagnostics.rebuildable_projections == 8
    assert diagnostics.dependency_failures == 0
    assert diagnostics.overall_health == "healthy"
    projection_by_type = {
        projection.projection_type: projection
        for projection in diagnostics.projections
    }
    assert sorted(projection_by_type) == EXPECTED_EVALUATION_PROJECTIONS
    assert projection_by_type["evaluation_summary"].registered is True
    assert projection_by_type["evaluation_outcome_rollup"].registered is True
    assert projection_by_type["evaluation_trend"].registered is True
    assert projection_by_type["evaluation_registry"].registered is True
    assert projection_by_type["evaluation_lineage"].registered is True
    assert projection_by_type["evaluation_coverage"].registered is True
    assert projection_by_type["evaluation_drift"].registered is True
    assert (
        projection_by_type["evaluation_intelligence_overview"].registered
        is True
    )
    assert projection_by_type["evaluation_summary"].rebuild_supported is True
    assert projection_by_type["evaluation_summary"].rebuildable is True
    assert projection_by_type["evaluation_summary"].health_status == "healthy"
    assert projection_by_type["evaluation_summary"].persisted is False
    assert projection_by_type["evaluation_summary"].route == (
        "/runtime/evaluation-summary"
    )
    assert projection_by_type["evaluation_outcome_rollup"].route == (
        "/runtime/evaluation-outcome-rollup"
    )
    assert projection_by_type["evaluation_trend"].route == (
        "/runtime/evaluation-trend"
    )
    assert projection_by_type["evaluation_registry"].route == (
        "/evaluation-registry/projection"
    )
    assert projection_by_type["evaluation_lineage"].route == (
        "/evaluation-lineage/projection"
    )
    assert projection_by_type["evaluation_coverage"].route == (
        "/evaluation-coverage/projection"
    )
    assert projection_by_type["evaluation_drift"].route == (
        "/evaluation-drift/projection"
    )
    assert projection_by_type["evaluation_intelligence_overview"].route == (
        "/evaluation-intelligence-overview/projection"
    )
    assert (
        projection_by_type["evaluation_intelligence_overview"].dependency_count
        == 4
    )
    assert (
        projection_by_type[
            "evaluation_intelligence_overview"
        ].dependency_status
        == "healthy"
    )


def test_diagnostics_route_works() -> None:
    response = TestClient(app).get("/runtime/evaluation-diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert {
        "evaluation_count",
        "result_count",
        "dimension_count",
        "target_snapshot_count",
        "evaluations_without_results_count",
        "evaluations_without_target_snapshot_count",
        "registered_projection_types",
        "projections",
        "total_projections",
        "healthy_projections",
        "unhealthy_projections",
        "rebuildable_projections",
        "dependency_failures",
        "overall_health",
        "generated_at",
    } == set(body)
    assert body["overall_health"] == "healthy"


def test_diagnostics_alias_routes_work() -> None:
    client = TestClient(app)

    diagnostics = client.get("/evaluation-diagnostics")
    projection = client.get("/evaluation-diagnostics/projection")

    assert diagnostics.status_code == 200
    assert projection.status_code == 200
    assert diagnostics.json()["overall_health"] == "healthy"
    assert projection.json()["overall_health"] == "healthy"
    assert projection.json()["total_projections"] == 8


def test_projection_registry_contains_evaluation_projection_types() -> None:
    projection_types = projection_registry.list_projection_types()

    for projection_type in EXPECTED_EVALUATION_PROJECTIONS:
        assert projection_type in projection_types


def test_runtime_projection_diagnostics_include_evaluation_projections() -> None:
    response = TestClient(app).get("/runtime/projection-diagnostics")

    assert response.status_code == 200
    projection_types = response.json()["projection_types"]
    for projection_type in EXPECTED_EVALUATION_PROJECTIONS:
        assert projection_type in projection_types


def test_runtime_diagnostics_include_evaluation_subsystem(monkeypatch) -> None:
    service = DiagnosticsService(
        evaluation_diagnostics=evaluation_diagnostics_service
    )
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

    evaluations = service.runtime_summary()["evaluations"]

    assert evaluations == {
        "projection_count": 8,
        "healthy_projections": 8,
        "unhealthy_projections": 0,
        "dependency_failures": 0,
        "overall_health": "healthy",
    }


def test_query_health_and_executor_diagnostics_include_evaluations() -> None:
    client = TestClient(app)

    health = client.get("/runtime/query-health")
    executor = client.get("/runtime/query-executor/diagnostics")

    assert health.status_code == 200
    assert executor.status_code == 200
    assert health.json()["unhealthy_entries"] == []
    executable_query_ids = executor.json()["executable_query_ids"]
    assert "runtime.evaluation_coverage" in executable_query_ids
    assert "runtime.evaluation_drift" in executable_query_ids
    assert (
        "runtime.evaluation_intelligence_overview" in executable_query_ids
    )
