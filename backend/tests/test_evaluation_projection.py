from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.schema import DecisionRecordRecord
from app.main import app
from app.runtime.projection_registry import projection_registry
from app.models.evaluation_record import EvaluationRecordCreate
from app.services.evaluation_record_projection_builder_service import (
    EVALUATION_RECORD_PROJECTION_TYPE,
    EvaluationRecordProjectionBuilderService,
)
from app.services.evaluation_record_service import EvaluationRecordService
from app.services.artifact_service import ArtifactService, artifact_service
from app.services.decision_record_service import DecisionRecordService
from app.services.evaluation_projection_builder_service import (
    EVALUATION_SUMMARY_PROJECTION_TYPE,
    EvaluationProjectionBuilderService,
)
from app.services.evaluation_projection_service import (
    EvaluationProjectionService,
)
from app.services.evaluation_service import EvaluationService
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


def make_projection_fixture(tmp_path, clock=None):
    artifacts = ArtifactService(tmp_path / "artifacts.db")
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    decisions = DecisionRecordService(tmp_path / "decisions.db")
    evaluations = EvaluationService(
        tmp_path / "evaluations.db",
        artifacts=artifacts,
        decisions=decisions,
        sessions=sessions,
    )
    builder = EvaluationProjectionBuilderService(
        evaluations=evaluations,
        clock=clock,
    )
    service = EvaluationProjectionService(builder=builder)
    return evaluations, builder, service, artifacts, decisions, sessions


def test_projection_summary_builds_from_evaluation_results(tmp_path) -> None:
    built_at = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    evaluations, builder, _, artifacts, decisions, sessions = make_projection_fixture(
        tmp_path,
        clock=lambda: built_at,
    )
    session = sessions.create_session("task-projection")
    artifact = artifacts.create_artifact_without_event(
        path="reports/projection.md",
        kind="report",
        task_id=session.task_id,
    )
    decision_id = "decision-projection"
    with decisions.session_factory() as db:
        decision = DecisionRecordRecord(
            decision_id=decision_id,
            session_id=session.id,
            task_id=session.task_id,
            decision_type="recommendation_selection",
            selected_entity_id="recommendation-projection",
            selected_entity_type="planner_recommendation",
            rationale="Projection target",
            created_at=datetime(2026, 6, 16, tzinfo=UTC),
        )
        db.add(decision)
        db.commit()
    correctness = evaluations.create_dimension(
        "Correctness",
        "Correctness signal",
    )
    helpfulness = evaluations.create_dimension(
        "Helpfulness",
        "Helpfulness signal",
    )
    evaluation = evaluations.create_evaluation(
        session_id=session.id,
        decision_id=decision_id,
        artifact_id=artifact.id,
        evaluation_type="manual_review",
        status="recorded",
    )
    evaluations.add_result(
        evaluation.id,
        correctness.id,
        1.0,
        "First correctness score",
    )
    evaluations.add_result(
        evaluation.id,
        correctness.id,
        3.0,
        "Second correctness score",
    )
    latest = evaluations.add_result(
        evaluation.id,
        helpfulness.id,
        5.0,
        "Helpfulness score",
    )

    projections = builder.build({})

    assert len(projections) == 1
    summary = projections[0]
    assert summary.metadata.projection_type == EVALUATION_SUMMARY_PROJECTION_TYPE
    assert summary.metadata.built_at == built_at
    assert summary.evaluation_id == evaluation.id
    assert summary.session_id == session.id
    assert summary.decision_id == decision_id
    assert summary.artifact_id == artifact.id
    assert summary.target_type == "artifact"
    assert summary.target_id == artifact.id
    assert summary.target_summary == "reports/projection.md"
    assert summary.evaluation_type == "manual_review"
    assert summary.status == "recorded"
    assert summary.result_count == 3
    assert summary.average_score == 3.0
    assert summary.min_score == 1.0
    assert summary.max_score == 5.0
    assert summary.created_at == evaluation.created_at.isoformat()
    assert summary.updated_at == latest.created_at.isoformat()
    dimension_by_id = {
        dimension.dimension_id: dimension for dimension in summary.dimensions
    }
    assert sorted(dimension_by_id) == sorted([correctness.id, helpfulness.id])
    assert dimension_by_id[correctness.id].dimension_name == "Correctness"
    assert dimension_by_id[correctness.id].result_count == 2
    assert dimension_by_id[correctness.id].average_score == 2.0
    assert dimension_by_id[correctness.id].latest_score == 3.0
    assert dimension_by_id[helpfulness.id].dimension_name == "Helpfulness"
    assert dimension_by_id[helpfulness.id].result_count == 1
    assert dimension_by_id[helpfulness.id].average_score == 5.0
    assert dimension_by_id[helpfulness.id].latest_score == 5.0


def test_projection_handles_evaluation_with_no_results(tmp_path) -> None:
    evaluations, builder, _, _, _, sessions = make_projection_fixture(tmp_path)
    session = sessions.create_session("session-empty-task")
    evaluation = evaluations.create_evaluation(
        session_id=session.id,
        evaluation_type="manual_review",
        status="draft",
    )

    projections = builder.build({})

    assert len(projections) == 1
    summary = projections[0]
    assert summary.evaluation_id == evaluation.id
    assert summary.result_count == 0
    assert summary.average_score is None
    assert summary.min_score is None
    assert summary.max_score is None
    assert summary.dimensions == []
    assert summary.target_type == "session"
    assert summary.target_id == session.id
    assert summary.target_summary == "session-empty-task"
    assert summary.updated_at == evaluation.created_at.isoformat()


def test_projection_service_filters(tmp_path) -> None:
    evaluations, _, service, artifacts, _, sessions = make_projection_fixture(
        tmp_path
    )
    session = sessions.create_session("session-1-task")
    artifact = artifacts.create_artifact_without_event(
        path="reports/filter.md",
        kind="report",
        task_id="artifact-task",
    )
    first = evaluations.create_evaluation(
        session_id=session.id,
        decision_id="decision-1",
        evaluation_type="manual_review",
        status="recorded",
    )
    second = evaluations.create_evaluation(
        artifact_id=artifact.id,
        evaluation_type="artifact_review",
        status="draft",
    )

    assert [
        item.evaluation_id
        for item in service.list_evaluation_summaries(session_id=session.id)
    ] == [first.id]
    assert [
        item.evaluation_id
        for item in service.list_evaluation_summaries(artifact_id=artifact.id)
    ] == [second.id]
    assert [
        item.evaluation_id
        for item in service.list_evaluation_summaries(status="draft")
    ] == [second.id]


def test_projection_routes_list_and_detail() -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("task-route-target")
    artifact = artifact_service.create_artifact_without_event(
        path="reports/route-target.md",
        kind="report",
        task_id=session.task_id,
    )
    dimension = client.post(
        "/evaluation-dimensions",
        json={
            "name": "Correctness",
            "description": "Correctness signal",
        },
    ).json()
    evaluation = client.post(
        "/evaluations",
        json={
            "session_id": session.id,
            "artifact_id": artifact.id,
            "evaluation_type": "manual_review",
            "status": "recorded",
        },
    ).json()
    client.post(
        f"/evaluations/{evaluation['id']}/results",
        json={
            "dimension_id": dimension["id"],
            "score": 2.5,
            "rationale": "Route-added result",
        },
    )

    listed = client.get(
        f"/runtime/evaluation-projections?session_id={session.id}"
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert len(listed_body) == 1
    assert listed_body[0]["evaluation_id"] == evaluation["id"]
    assert listed_body[0]["target_type"] == "artifact"
    assert listed_body[0]["target_id"] == artifact.id
    assert listed_body[0]["target_summary"] == "reports/route-target.md"
    assert listed_body[0]["result_count"] == 1
    assert listed_body[0]["average_score"] == 2.5

    detail = client.get(
        f"/runtime/evaluation-projections/{evaluation['id']}"
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["evaluation_id"] == evaluation["id"]
    assert detail_body["target_type"] == "artifact"
    assert detail_body["target_id"] == artifact.id
    assert detail_body["target_summary"] == "reports/route-target.md"
    assert detail_body["dimensions"][0]["dimension_id"] == dimension["id"]
    assert detail_body["dimensions"][0]["latest_score"] == 2.5


def test_projection_detail_route_missing_projection() -> None:
    response = TestClient(app).get(
        "/runtime/evaluation-projections/missing-evaluation"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Evaluation summary projection not found: missing-evaluation"
        )
    }


def test_projection_registry_includes_evaluation_summary() -> None:
    assert EVALUATION_SUMMARY_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
    schema = projection_registry.get_schema(EVALUATION_SUMMARY_PROJECTION_TYPE)
    assert schema.projection_type == EVALUATION_SUMMARY_PROJECTION_TYPE
    assert schema.builder_name == "EvaluationSummaryProjectionBuilderService"


def create_evaluation_record(
    service: EvaluationRecordService,
    *,
    target_type: str,
    target_id: str,
    evaluation_type: str,
    outcome: str,
    score: float | None,
) -> None:
    service.create_record(
        EvaluationRecordCreate(
            target_type=target_type,  # type: ignore[arg-type]
            target_id=target_id,
            evaluation_type=evaluation_type,
            outcome=outcome,  # type: ignore[arg-type]
            score=score,
            evaluator="governance",
        )
    )


def test_evaluation_record_projection_rebuilds_deterministically() -> None:
    built_at = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    evaluations = EvaluationRecordService()
    builder = EvaluationRecordProjectionBuilderService(
        evaluations=evaluations,
        clock=lambda: built_at,
    )
    create_evaluation_record(
        evaluations,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
        score=4.0,
    )
    create_evaluation_record(
        evaluations,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
        score=2.0,
    )
    create_evaluation_record(
        evaluations,
        target_type="artifact",
        target_id="artifact-2",
        evaluation_type="quality_review",
        outcome="accepted",
        score=None,
    )

    first = builder.build({})
    second = builder.build({})

    assert first == second
    assert first.metadata.projection_type == EVALUATION_RECORD_PROJECTION_TYPE
    assert first.metadata.built_at == built_at
    assert first.metadata.reconstruction.rebuildable is True
    assert first.total_evaluations == 3
    assert first.evaluations_by_type == {
        "quality_review": 2,
        "safety_review": 1,
    }
    assert first.evaluations_by_outcome == {
        "accepted": 1,
        "failure": 1,
        "success": 1,
    }
    assert first.evaluations_by_target_type == {
        "artifact": 2,
        "decision": 1,
    }
    assert first.average_score_by_evaluation_type == {
        "quality_review": 4.0,
        "safety_review": 2.0,
    }
    assert first.average_score_by_target_type == {
        "artifact": 4.0,
        "decision": 2.0,
    }


def test_evaluation_record_projection_filters_source_records() -> None:
    evaluations = EvaluationRecordService()
    builder = EvaluationRecordProjectionBuilderService(
        evaluations=evaluations,
    )
    create_evaluation_record(
        evaluations,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
        score=4.0,
    )
    create_evaluation_record(
        evaluations,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="quality_review",
        outcome="failure",
        score=2.0,
    )

    projection = builder.build({"target_type": "artifact"})

    assert projection.total_evaluations == 1
    assert projection.evaluations_by_target_type == {"artifact": 1}
    assert projection.evaluations_by_outcome == {"success": 1}
    assert projection.average_score_by_evaluation_type == {
        "quality_review": 4.0
    }


def test_evaluation_record_projection_summary_route() -> None:
    client = TestClient(app)
    client.post(
        "/runtime/evaluations",
        json={
            "target_type": "artifact",
            "target_id": "artifact-route-1",
            "evaluation_type": "quality_review",
            "outcome": "success",
            "score": 3.0,
            "evaluator": "governance",
        },
    )
    client.post(
        "/runtime/evaluations",
        json={
            "target_type": "artifact",
            "target_id": "artifact-route-2",
            "evaluation_type": "quality_review",
            "outcome": "failure",
            "score": 1.0,
            "evaluator": "governance",
        },
    )

    response = client.get(
        "/runtime/evaluation-projections/summary"
        "?evaluation_type=quality_review"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_evaluations"] == 2
    assert body["evaluations_by_type"] == {"quality_review": 2}
    assert body["evaluations_by_outcome"] == {
        "failure": 1,
        "success": 1,
    }
    assert body["evaluations_by_target_type"] == {"artifact": 2}
    assert body["average_score_by_evaluation_type"] == {
        "quality_review": 2.0
    }
    assert body["average_score_by_target_type"] == {"artifact": 2.0}
    assert body["metadata"]["projection_type"] == (
        EVALUATION_RECORD_PROJECTION_TYPE
    )
