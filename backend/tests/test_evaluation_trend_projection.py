from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.schema import (
    EvaluationRecord,
    EvaluationResultRecord,
    EvaluationTargetSnapshotRecord,
)
from app.main import app
from app.runtime.projection_registry import projection_registry
from app.services.artifact_service import ArtifactService
from app.services.decision_record_service import DecisionRecordService
from app.services.evaluation_service import EvaluationService
from app.services.evaluation_trend_projection_builder_service import (
    EVALUATION_TREND_PROJECTION_TYPE,
    EvaluationTrendProjectionBuilderService,
)
from app.services.evaluation_trend_projection_service import (
    EvaluationTrendProjectionService,
)
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
    builder = EvaluationTrendProjectionBuilderService(
        evaluations=evaluations,
        clock=clock,
    )
    service = EvaluationTrendProjectionService(builder=builder)
    return evaluations, artifacts, sessions, builder, service


def create_artifact_evaluation(
    evaluations,
    artifacts,
    session,
    *,
    path: str,
    evaluation_type: str,
    status: str,
    dimension,
    scores: list[float],
) -> None:
    artifact = artifacts.create_artifact_without_event(
        path=path,
        kind="report",
        task_id=session.task_id,
    )
    evaluation = evaluations.create_evaluation(
        session_id=session.id,
        artifact_id=artifact.id,
        evaluation_type=evaluation_type,
        status=status,
    )
    with evaluations.session_factory() as db:
        record = db.get(EvaluationRecord, evaluation.id)
        record.created_at = datetime.fromisoformat(path.replace("ts:", ""))
        db.commit()
    with evaluations.session_factory() as db:
        snapshot = db.get(EvaluationTargetSnapshotRecord, evaluation.id)
        snapshot.created_at = datetime.fromisoformat(path.replace("ts:", ""))
        db.commit()
    for score in scores:
        result = evaluations.add_result(
            evaluation.id,
            dimension.id,
            score,
            f"Score {score}",
        )
        with evaluations.session_factory() as db:
            result_record = db.get(EvaluationResultRecord, result.id)
            result_record.created_at = datetime.fromisoformat(
                path.replace("ts:", "")
            )
            db.commit()


def test_daily_weekly_and_monthly_buckets(tmp_path) -> None:
    built_at = datetime(2026, 6, 16, 18, 0, tzinfo=UTC)
    evaluations, artifacts, sessions, builder, _ = make_fixture(
        tmp_path,
        clock=lambda: built_at,
    )
    session = sessions.create_session("task-trend")
    dimension = evaluations.create_dimension("Correctness", "Signal")

    create_artifact_evaluation(
        evaluations,
        artifacts,
        session,
        path="ts:2026-06-01T10:00:00+00:00",
        evaluation_type="artifact_review",
        status="recorded",
        dimension=dimension,
        scores=[1.0, 3.0],
    )
    create_artifact_evaluation(
        evaluations,
        artifacts,
        session,
        path="ts:2026-06-03T12:00:00+00:00",
        evaluation_type="artifact_review",
        status="approved",
        dimension=dimension,
        scores=[5.0],
    )
    create_artifact_evaluation(
        evaluations,
        artifacts,
        session,
        path="ts:2026-07-04T09:00:00+00:00",
        evaluation_type="manual_review",
        status="recorded",
        dimension=dimension,
        scores=[],
    )

    daily = builder.build({"granularity": "day"})
    weekly = builder.build({"granularity": "week"})
    monthly = builder.build({"granularity": "month"})

    assert [bucket.bucket_start for bucket in daily] == [
        "2026-06-01T00:00:00+00:00",
        "2026-06-03T00:00:00+00:00",
        "2026-07-04T00:00:00+00:00",
    ]
    assert [bucket.bucket_start for bucket in weekly] == [
        "2026-06-01T00:00:00+00:00",
        "2026-06-29T00:00:00+00:00",
    ]
    assert [bucket.bucket_start for bucket in monthly] == [
        "2026-06-01T00:00:00+00:00",
        "2026-07-01T00:00:00+00:00",
    ]
    june = monthly[0]
    assert june.bucket_granularity == "month"
    assert june.evaluation_count == 2
    assert june.result_count == 3
    assert june.average_score == 3.0
    assert june.min_score == 1.0
    assert june.max_score == 5.0
    assert june.target_types == ["artifact"]
    assert june.evaluation_types == ["artifact_review"]
    assert june.dimensions[0].dimension_id == dimension.id
    assert june.dimensions[0].result_count == 3
    assert june.dimensions[0].average_score == 3.0
    assert june.dimensions[0].min_score == 1.0
    assert june.dimensions[0].max_score == 5.0
    july = monthly[1]
    assert july.evaluation_count == 1
    assert july.result_count == 0
    assert july.average_score is None
    assert july.dimensions == []


def test_trend_filters_by_target_type_and_evaluation_type(tmp_path) -> None:
    evaluations, artifacts, sessions, _, service = make_fixture(tmp_path)
    session = sessions.create_session("task-filter")
    dimension = evaluations.create_dimension("Quality", "Signal")
    create_artifact_evaluation(
        evaluations,
        artifacts,
        session,
        path="ts:2026-06-05T10:00:00+00:00",
        evaluation_type="artifact_review",
        status="recorded",
        dimension=dimension,
        scores=[2.0],
    )
    create_artifact_evaluation(
        evaluations,
        artifacts,
        session,
        path="ts:2026-06-06T10:00:00+00:00",
        evaluation_type="manual_review",
        status="recorded",
        dimension=dimension,
        scores=[4.0],
    )

    artifact_only = service.list_trend_buckets(target_type="artifact")
    manual_only = service.list_trend_buckets(evaluation_type="manual_review")

    assert len(artifact_only) == 2
    assert len(manual_only) == 1
    assert manual_only[0].evaluation_types == ["manual_review"]


def test_trend_route_returns_buckets(tmp_path) -> None:
    evaluations, artifacts, sessions, _, _ = make_fixture(tmp_path)
    session = sessions.create_session("task-route")
    dimension = evaluations.create_dimension("Quality", "Signal")
    create_artifact_evaluation(
        evaluations,
        artifacts,
        session,
        path="ts:2026-06-10T10:00:00+00:00",
        evaluation_type="artifact_review",
        status="recorded",
        dimension=dimension,
        scores=[2.5, 4.5],
    )

    response = TestClient(app).get(
        "/runtime/evaluation-trends?granularity=day&target_type=artifact"
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["bucket_start"] == "2026-06-10T00:00:00+00:00"
    assert body[0]["evaluation_count"] == 1
    assert body[0]["result_count"] == 2
    assert body[0]["average_score"] == 3.5


def test_registry_includes_evaluation_trend() -> None:
    assert EVALUATION_TREND_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
