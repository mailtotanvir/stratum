from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_record import EvaluationRecord, EvaluationRecordCreate
from app.runtime.projection_registry import projection_registry
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE,
    EvaluationOutcomeRollupProjectionBuilderService,
    evaluation_outcome_rollup_projection_builder_service,
)
from app.services.evaluation_record_service import EvaluationRecordService


def create_record(
    service: EvaluationRecordService,
    *,
    target_type: str,
    target_id: str,
    evaluation_type: str,
    outcome: str,
) -> None:
    service.create_record(
        EvaluationRecordCreate(
            target_type=target_type,  # type: ignore[arg-type]
            target_id=target_id,
            evaluation_type=evaluation_type,
            outcome=outcome,  # type: ignore[arg-type]
            evaluator="governance",
        )
    )


def add_unsupported_outcome_record(
    service: EvaluationRecordService,
    *,
    outcome: str,
) -> None:
    record = EvaluationRecord.model_construct(
        session_id=None,
        task_id=None,
        target_type="artifact",
        target_id="artifact-unsupported",
        evaluation_type="quality_review",
        outcome=outcome,
        score=None,
        evaluator="governance",
        rationale=None,
        metadata={},
        evaluation_id="unsupported-outcome-record",
        created_at=datetime(2026, 6, 20, 14, 0, tzinfo=UTC),
    )
    service._records[record.evaluation_id] = record  # noqa: SLF001


def test_outcome_rollup_counts_and_rates_are_deterministic() -> None:
    generated_at = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
    evaluations = EvaluationRecordService()
    builder = EvaluationOutcomeRollupProjectionBuilderService(
        evaluations=evaluations,
        clock=lambda: generated_at,
    )
    for outcome in [
        "success",
        "success",
        "failure",
        "accepted",
        "rejected",
        "reverted",
        "inconclusive",
    ]:
        create_record(
            evaluations,
            target_type="artifact",
            target_id=f"artifact-{outcome}",
            evaluation_type="quality_review",
            outcome=outcome,
        )

    first = builder.build({})
    second = builder.build({})

    assert first == second
    assert first.metadata.projection_type == (
        EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE
    )
    assert first.metadata.builder_name == (
        "EvaluationOutcomeRollupProjectionBuilderService"
    )
    assert first.metadata.reconstruction.authoritative_source == (
        "runtime_evaluation_records"
    )
    assert first.generated_at == generated_at
    assert first.total_evaluations == 7
    assert first.success_count == 2
    assert first.failure_count == 1
    assert first.accepted_count == 1
    assert first.rejected_count == 1
    assert first.reverted_count == 1
    assert first.inconclusive_count == 1
    assert first.success_rate == 2 / 7
    assert first.failure_rate == 1 / 7
    assert first.acceptance_rate == 1 / 7
    assert first.rejection_rate == 1 / 7
    assert first.reversion_rate == 1 / 7
    assert first.inconclusive_rate == 1 / 7


def test_outcome_rollup_empty_state_does_not_divide_by_zero() -> None:
    generated_at = datetime(2026, 6, 20, 13, 0, tzinfo=UTC)
    builder = EvaluationOutcomeRollupProjectionBuilderService(
        evaluations=EvaluationRecordService(),
        clock=lambda: generated_at,
    )

    projection = builder.build({})

    assert projection.total_evaluations == 0
    assert projection.success_count == 0
    assert projection.failure_count == 0
    assert projection.accepted_count == 0
    assert projection.rejected_count == 0
    assert projection.reverted_count == 0
    assert projection.inconclusive_count == 0
    assert projection.success_rate == 0.0
    assert projection.failure_rate == 0.0
    assert projection.acceptance_rate == 0.0
    assert projection.rejection_rate == 0.0
    assert projection.reversion_rate == 0.0
    assert projection.inconclusive_rate == 0.0
    assert projection.generated_at == generated_at


def test_outcome_rollup_ignores_unsupported_outcomes_deterministically() -> None:
    evaluations = EvaluationRecordService()
    builder = EvaluationOutcomeRollupProjectionBuilderService(
        evaluations=evaluations,
    )
    create_record(
        evaluations,
        target_type="artifact",
        target_id="artifact-success",
        evaluation_type="quality_review",
        outcome="success",
    )
    add_unsupported_outcome_record(evaluations, outcome="partially_successful")

    projection = builder.build({})

    assert projection.total_evaluations == 2
    assert projection.success_count == 1
    assert projection.failure_count == 0
    assert projection.accepted_count == 0
    assert projection.rejected_count == 0
    assert projection.reverted_count == 0
    assert projection.inconclusive_count == 0
    assert projection.success_rate == 0.5
    assert projection.failure_rate == 0.0


def test_outcome_rollup_route_rebuilds_projection() -> None:
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

    response = client.get(
        "/runtime/evaluation-outcome-rollup"
        "?evaluation_type=quality_review"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_evaluations"] == 2
    assert body["success_count"] == 1
    assert body["failure_count"] == 1
    assert body["success_rate"] == 0.5
    assert body["failure_rate"] == 0.5
    assert body["metadata"]["projection_type"] == (
        EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE
    )
    assert "generated_at" in body


def test_outcome_rollup_is_registered_and_discoverable() -> None:
    assert EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )
    assert (
        projection_registry.get(EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE)
        is evaluation_outcome_rollup_projection_builder_service
    )
    schema = projection_registry.get_schema(
        EVALUATION_OUTCOME_ROLLUP_PROJECTION_TYPE
    )
    assert schema.builder_name == (
        "EvaluationOutcomeRollupProjectionBuilderService"
    )
    assert schema.reconstruction.authoritative_source == (
        "runtime_evaluation_records"
    )

    response = TestClient(app).get(
        "/runtime/projections/registry/evaluation_outcome_rollup"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "/runtime/evaluation-outcome-rollup"
    assert body["supported_filters"] == [
        "target_type",
        "target_id",
        "evaluation_type",
        "outcome",
    ]
