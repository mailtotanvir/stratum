from fastapi.testclient import TestClient

from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.artifact_service import ArtifactService
from app.services.evaluation_diagnostics_service import (
    evaluation_diagnostics_service,
)
from app.services.evaluation_service import EvaluationService
from app.services.runtime_session_service import RuntimeSessionService


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

    assert diagnostics.registered_projection_types == [
        "evaluation_outcome_rollup",
        "evaluation_summary",
        "evaluation_trend",
    ]
    projection_by_type = {
        projection.projection_type: projection
        for projection in diagnostics.projections
    }
    assert projection_by_type["evaluation_summary"].registered is True
    assert projection_by_type["evaluation_outcome_rollup"].registered is True
    assert projection_by_type["evaluation_trend"].registered is True
    assert projection_by_type["evaluation_summary"].rebuildable is True
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
        "generated_at",
    } == set(body)


def test_projection_registry_contains_evaluation_projection_types() -> None:
    assert "evaluation_summary" in projection_registry.list_projection_types()
    assert "evaluation_outcome_rollup" in projection_registry.list_projection_types()
    assert "evaluation_trend" in projection_registry.list_projection_types()
