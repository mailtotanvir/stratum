from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_record import EvaluationRecordCreate
from app.runtime.projection_registry import projection_registry
from app.services.evaluation_record_service import EvaluationRecordService
from app.services.evaluation_summary_projection_builder_service import (
    EVALUATION_SUMMARY_PROJECTION_TYPE,
    EvaluationSummaryProjectionBuilderService,
    evaluation_summary_projection_builder_service,
)


def create_record(
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


def test_evaluation_summary_rebuilds_deterministically_from_records() -> None:
    generated_at = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
    evaluations = EvaluationRecordService()
    builder = EvaluationSummaryProjectionBuilderService(
        evaluations=evaluations,
        clock=lambda: generated_at,
    )
    create_record(
        evaluations,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
        score=4.0,
    )
    create_record(
        evaluations,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
        score=2.0,
    )
    create_record(
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
    assert first.metadata.projection_type == EVALUATION_SUMMARY_PROJECTION_TYPE
    assert first.metadata.builder_name == (
        "EvaluationSummaryProjectionBuilderService"
    )
    assert first.metadata.reconstruction.authoritative_source == (
        "runtime_evaluation_records"
    )
    assert first.generated_at == generated_at
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


def test_evaluation_summary_empty_state() -> None:
    generated_at = datetime(2026, 6, 20, 13, 0, tzinfo=UTC)
    builder = EvaluationSummaryProjectionBuilderService(
        evaluations=EvaluationRecordService(),
        clock=lambda: generated_at,
    )

    projection = builder.build({})

    assert projection.total_evaluations == 0
    assert projection.evaluations_by_type == {}
    assert projection.evaluations_by_outcome == {}
    assert projection.evaluations_by_target_type == {}
    assert projection.average_score_by_evaluation_type == {}
    assert projection.average_score_by_target_type == {}
    assert projection.generated_at == generated_at


def test_evaluation_summary_filters_source_records() -> None:
    evaluations = EvaluationRecordService()
    builder = EvaluationSummaryProjectionBuilderService(
        evaluations=evaluations,
    )
    create_record(
        evaluations,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
        score=4.0,
    )
    create_record(
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


def test_evaluation_summary_route_rebuilds_projection() -> None:
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
        "/runtime/evaluation-summary?evaluation_type=quality_review"
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
        EVALUATION_SUMMARY_PROJECTION_TYPE
    )
    assert "generated_at" in body


def test_evaluation_summary_is_registered_and_discoverable() -> None:
    assert EVALUATION_SUMMARY_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
    assert (
        projection_registry.get(EVALUATION_SUMMARY_PROJECTION_TYPE)
        is evaluation_summary_projection_builder_service
    )
    schema = projection_registry.get_schema(EVALUATION_SUMMARY_PROJECTION_TYPE)
    assert schema.builder_name == "EvaluationSummaryProjectionBuilderService"
    assert schema.reconstruction.authoritative_source == (
        "runtime_evaluation_records"
    )

    response = TestClient(app).get(
        "/runtime/projections/registry/evaluation_summary"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "/runtime/evaluation-summary"
    assert body["supported_filters"] == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
