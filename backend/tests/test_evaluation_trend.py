from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_record import EvaluationRecord
from app.runtime.projection_registry import projection_registry
from app.services.evaluation_record_service import EvaluationRecordService
from app.services.evaluation_trend_projection_v2_builder_service import (
    EVALUATION_TREND_PROJECTION_TYPE,
    EvaluationTrendProjectionBuilderService,
    evaluation_trend_projection_builder_service,
)


def add_record(
    service: EvaluationRecordService,
    *,
    evaluation_id: str,
    created_at: datetime,
    outcome: str,
) -> None:
    record = EvaluationRecord.model_construct(
        session_id=None,
        task_id=None,
        target_type="artifact",
        target_id=evaluation_id,
        evaluation_type="quality_review",
        outcome=outcome,
        score=None,
        evaluator="governance",
        rationale=None,
        metadata={},
        evaluation_id=evaluation_id,
        created_at=created_at,
    )
    service._records[record.evaluation_id] = record  # noqa: SLF001


def test_daily_buckets_include_outcome_counts_and_rates() -> None:
    generated_at = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
    evaluations = EvaluationRecordService()
    builder = EvaluationTrendProjectionBuilderService(
        evaluations=evaluations,
        clock=lambda: generated_at,
    )
    add_record(
        evaluations,
        evaluation_id="evaluation-1",
        created_at=datetime(2026, 6, 18, 10, 30, tzinfo=UTC),
        outcome="success",
    )
    add_record(
        evaluations,
        evaluation_id="evaluation-2",
        created_at=datetime(2026, 6, 18, 18, 0, tzinfo=UTC),
        outcome="failure",
    )
    add_record(
        evaluations,
        evaluation_id="evaluation-3",
        created_at=datetime(2026, 6, 19, 9, 0, tzinfo=UTC),
        outcome="accepted",
    )
    add_record(
        evaluations,
        evaluation_id="evaluation-4",
        created_at=datetime(2026, 6, 19, 17, 0, tzinfo=UTC),
        outcome="rejected",
    )
    add_record(
        evaluations,
        evaluation_id="evaluation-5",
        created_at=datetime(2026, 6, 19, 20, 0, tzinfo=UTC),
        outcome="inconclusive",
    )

    first = builder.build({"granularity": "day"})
    second = builder.build({"granularity": "day"})

    assert first == second
    assert first.metadata.projection_type == EVALUATION_TREND_PROJECTION_TYPE
    assert first.metadata.builder_name == "EvaluationTrendProjectionBuilderService"
    assert first.metadata.reconstruction.authoritative_source == (
        "runtime_evaluation_records"
    )
    assert first.bucket_granularity == "day"
    assert first.generated_at == generated_at
    assert len(first.buckets) == 2

    june_18 = first.buckets[0]
    assert june_18.bucket_start == "2026-06-18T00:00:00+00:00"
    assert june_18.bucket_end == "2026-06-19T00:00:00+00:00"
    assert june_18.total_evaluations == 2
    assert june_18.evaluations_by_outcome == {
        "failure": 1,
        "success": 1,
    }
    assert june_18.success_rate == 0.5
    assert june_18.failure_rate == 0.5
    assert june_18.acceptance_rate == 0.0

    june_19 = first.buckets[1]
    assert june_19.bucket_start == "2026-06-19T00:00:00+00:00"
    assert june_19.bucket_end == "2026-06-20T00:00:00+00:00"
    assert june_19.total_evaluations == 3
    assert june_19.evaluations_by_outcome == {
        "accepted": 1,
        "inconclusive": 1,
        "rejected": 1,
    }
    assert june_19.acceptance_rate == 1 / 3
    assert june_19.rejection_rate == 1 / 3
    assert june_19.inconclusive_rate == 1 / 3
    assert june_19.success_rate == 0.0


def test_trend_empty_state_returns_stable_empty_response() -> None:
    generated_at = datetime(2026, 6, 20, 13, 0, tzinfo=UTC)
    builder = EvaluationTrendProjectionBuilderService(
        evaluations=EvaluationRecordService(),
        clock=lambda: generated_at,
    )

    projection = builder.build({"granularity": "day"})

    assert projection.bucket_granularity == "day"
    assert projection.buckets == []
    assert projection.generated_at == generated_at


def test_invalid_granularity_falls_back_to_day() -> None:
    evaluations = EvaluationRecordService()
    builder = EvaluationTrendProjectionBuilderService(evaluations=evaluations)
    add_record(
        evaluations,
        evaluation_id="evaluation-invalid-granularity",
        created_at=datetime(2026, 6, 18, 10, 30, tzinfo=UTC),
        outcome="reverted",
    )

    projection = builder.build({"granularity": "month"})

    assert projection.bucket_granularity == "day"
    assert projection.buckets[0].reversion_rate == 1.0


def test_trend_route_rebuilds_projection() -> None:
    client = TestClient(app)
    client.post(
        "/runtime/evaluations",
        json={
            "target_type": "artifact",
            "target_id": "artifact-route-1",
            "evaluation_type": "quality_review",
            "outcome": "success",
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
            "evaluator": "governance",
        },
    )

    response = client.get("/runtime/evaluation-trend?granularity=day")

    assert response.status_code == 200
    body = response.json()
    assert body["bucket_granularity"] == "day"
    assert len(body["buckets"]) == 1
    assert body["buckets"][0]["total_evaluations"] == 2
    assert body["buckets"][0]["evaluations_by_outcome"] == {
        "failure": 1,
        "success": 1,
    }
    assert body["buckets"][0]["success_rate"] == 0.5
    assert body["buckets"][0]["failure_rate"] == 0.5
    assert body["metadata"]["projection_type"] == EVALUATION_TREND_PROJECTION_TYPE
    assert "generated_at" in body


def test_trend_is_registered_and_discoverable() -> None:
    assert EVALUATION_TREND_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
    assert (
        projection_registry.get(EVALUATION_TREND_PROJECTION_TYPE)
        is evaluation_trend_projection_builder_service
    )
    schema = projection_registry.get_schema(EVALUATION_TREND_PROJECTION_TYPE)
    assert schema.builder_name == "EvaluationTrendProjectionBuilderService"
    assert schema.reconstruction.authoritative_source == (
        "runtime_evaluation_records"
    )

    response = TestClient(app).get(
        "/runtime/projections/registry/evaluation_trend"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "/runtime/evaluation-trend"
    assert body["supported_filters"] == ["granularity"]
