from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.schema import DecisionRecordRecord
from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.artifact_service import ArtifactService
from app.services.decision_record_service import DecisionRecordService
from app.services.evaluation_outcome_projection_builder_service import (
    EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
    EvaluationOutcomeProjectionBuilderService,
)
from app.services.evaluation_outcome_projection_service import (
    EvaluationOutcomeProjectionService,
)
from app.services.evaluation_service import EvaluationService
from app.services.runtime_session_service import RuntimeSessionService


def make_fixture(tmp_path, clock=None):
    artifacts = ArtifactService(tmp_path / "artifacts.db")
    decisions = DecisionRecordService(tmp_path / "decisions.db")
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    evaluations = EvaluationService(
        tmp_path / "evaluations.db",
        artifacts=artifacts,
        decisions=decisions,
        sessions=sessions,
    )
    builder = EvaluationOutcomeProjectionBuilderService(
        evaluations=evaluations,
        clock=clock,
    )
    service = EvaluationOutcomeProjectionService(builder=builder)
    return evaluations, artifacts, decisions, sessions, builder, service


def test_multiple_evaluations_for_same_artifact_roll_up_together(
    tmp_path,
) -> None:
    built_at = datetime(2026, 6, 16, 18, 0, tzinfo=UTC)
    evaluations, artifacts, _, sessions, builder, _ = make_fixture(
        tmp_path,
        clock=lambda: built_at,
    )
    session = sessions.create_session("task-rollup")
    artifact = artifacts.create_artifact_without_event(
        path="reports/rollup.md",
        kind="report",
        task_id=session.task_id,
    )
    correctness = evaluations.create_dimension(
        "Correctness",
        "Correctness signal",
    )
    helpfulness = evaluations.create_dimension(
        "Helpfulness",
        "Helpfulness signal",
    )
    first = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="recorded",
    )
    evaluations.add_result(
        first.id,
        correctness.id,
        1.0,
        "Low correctness",
    )
    second = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="approved",
    )
    second_result = evaluations.add_result(
        second.id,
        correctness.id,
        3.0,
        "Improved correctness",
    )
    latest_result = evaluations.add_result(
        second.id,
        helpfulness.id,
        5.0,
        "High helpfulness",
    )

    rollups = builder.build({})

    assert len(rollups) == 1
    rollup = rollups[0]
    assert rollup.metadata.projection_type == (
        EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE
    )
    assert rollup.metadata.built_at == built_at
    assert rollup.target_type == "artifact"
    assert rollup.target_id == artifact.id
    assert rollup.target_summary == "reports/rollup.md"
    assert rollup.evaluation_count == 2
    assert rollup.result_count == 3
    assert rollup.average_score == 3.0
    assert rollup.min_score == 1.0
    assert rollup.max_score == 5.0
    assert rollup.latest_evaluation_id == second.id
    assert rollup.latest_evaluation_status == "approved"
    assert rollup.latest_evaluated_at == second.created_at.isoformat()
    assert rollup.updated_at == latest_result.created_at.isoformat()
    dimension_by_id = {
        dimension.dimension_id: dimension for dimension in rollup.dimensions
    }
    assert dimension_by_id[correctness.id].evaluation_count == 2
    assert dimension_by_id[correctness.id].result_count == 2
    assert dimension_by_id[correctness.id].average_score == 2.0
    assert dimension_by_id[correctness.id].latest_score == 3.0
    assert dimension_by_id[helpfulness.id].evaluation_count == 1
    assert dimension_by_id[helpfulness.id].result_count == 1
    assert dimension_by_id[helpfulness.id].average_score == 5.0
    assert dimension_by_id[helpfulness.id].latest_score == 5.0


def test_evaluations_for_different_targets_stay_separate(tmp_path) -> None:
    evaluations, artifacts, decisions, sessions, _, service = make_fixture(
        tmp_path
    )
    session = sessions.create_session("task-separate")
    artifact = artifacts.create_artifact_without_event(
        path="reports/one.md",
        kind="report",
        task_id=session.task_id,
    )
    decision_id = "decision-separate"
    with decisions.session_factory() as db:
        db.add(
            DecisionRecordRecord(
                decision_id=decision_id,
                session_id=session.id,
                task_id=session.task_id,
                decision_type="recommendation_selection",
                selected_entity_id="recommendation-separate",
                selected_entity_type="planner_recommendation",
                rationale="Separate target",
                created_at=datetime(2026, 6, 16, tzinfo=UTC),
            )
        )
        db.commit()
    dimension = evaluations.create_dimension("Quality", "Quality signal")
    artifact_eval = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="recorded",
    )
    decision_eval = evaluations.create_evaluation(
        decision_id=decision_id,
        evaluation_type="manual_review",
        status="recorded",
    )
    evaluations.add_result(artifact_eval.id, dimension.id, 2.0, "Artifact")
    evaluations.add_result(decision_eval.id, dimension.id, 4.0, "Decision")

    rollups = service.list_outcome_rollups()

    assert sorted((item.target_type, item.target_id) for item in rollups) == [
        ("artifact", artifact.id),
        ("decision", decision_id),
    ]


def test_outcome_projection_routes_list_and_detail(tmp_path) -> None:
    evaluations, artifacts, _, sessions, _, _ = make_fixture(tmp_path)
    session = sessions.create_session("task-route")
    artifact = artifacts.create_artifact_without_event(
        path="reports/route-outcome.md",
        kind="report",
        task_id=session.task_id,
    )
    dimension = evaluations.create_dimension("Correctness", "Signal")
    first = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="recorded",
    )
    evaluations.add_result(first.id, dimension.id, 2.5, "First")
    second = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="approved",
    )
    evaluations.add_result(second.id, dimension.id, 4.5, "Second")

    client = TestClient(app)
    listed = client.get("/runtime/evaluation-outcomes?target_type=artifact")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["target_type"] == "artifact"
    assert body[0]["target_id"] == artifact.id
    assert body[0]["evaluation_count"] == 2
    assert body[0]["latest_evaluation_id"] == second.id

    detail = client.get(
        f"/runtime/evaluation-outcomes/artifact/{artifact.id}"
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["target_summary"] == "reports/route-outcome.md"
    assert detail_body["average_score"] == 3.5
    assert detail_body["min_score"] == 2.5
    assert detail_body["max_score"] == 4.5


def test_missing_outcome_target_returns_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/evaluation-outcomes/artifact/missing-artifact"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Evaluation outcome rollup not found: artifact/missing-artifact"
        )
    }


def test_registry_includes_evaluation_outcome_rollup() -> None:
    assert EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
