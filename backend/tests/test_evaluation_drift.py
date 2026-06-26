from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_drift import (
    EvaluationDriftBaselineCreate,
    EvaluationDriftObservationCreate,
)
from app.models.query_executor import QueryExecutionRequest
from app.services.evaluation_drift_projection_builder_service import (
    EVALUATION_DRIFT_PROJECTION_TYPE,
    EvaluationDriftProjectionBuilderService,
)
from app.services.evaluation_drift_service import (
    EvaluationDriftBaselineAlreadyExistsError,
    EvaluationDriftObservationAlreadyExistsError,
    EvaluationDriftService,
)
from app.services.event_service import EventService
from app.services.query_executor_service import query_executor_service
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


def make_service(tmp_path) -> EvaluationDriftService:
    return EvaluationDriftService(
        events=EventService(TraceService(tmp_path / "evaluation-drift.db"))
    )


def baseline_request(
    baseline_id: str = "baseline-policy-quality-v1",
    *,
    score: float = 0.8,
) -> EvaluationDriftBaselineCreate:
    return EvaluationDriftBaselineCreate(
        baseline_id=baseline_id,
        evaluation_id="eval-policy-quality",
        evaluation_name="Policy quality review",
        evaluation_version=1,
        baseline_score=score,
        baseline_pass_count=8,
        baseline_fail_count=2,
    )


def observation_request(
    observation_id: str = "observation-policy-quality-v1",
    *,
    score: float = 0.7,
) -> EvaluationDriftObservationCreate:
    return EvaluationDriftObservationCreate(
        observation_id=observation_id,
        evaluation_id="eval-policy-quality",
        evaluation_name="Policy quality review",
        evaluation_version=1,
        observed_score=score,
        observed_pass_count=7,
        observed_fail_count=3,
    )


def test_baseline_registration_is_event_backed(tmp_path) -> None:
    service = make_service(tmp_path)

    baseline = service.register_baseline(baseline_request())

    assert baseline.baseline_id == "baseline-policy-quality-v1"
    assert baseline.evaluation_id == "eval-policy-quality"
    assert baseline.evaluation_name == "Policy quality review"
    assert baseline.evaluation_version == 1
    assert baseline.baseline_score == 0.8
    assert baseline.baseline_pass_count == 8
    assert baseline.baseline_fail_count == 2
    assert service.get_baseline(baseline.baseline_id) == baseline
    assert service.list_baselines() == [baseline]


def test_observation_registration_is_event_backed(tmp_path) -> None:
    service = make_service(tmp_path)

    observation = service.register_observation(observation_request())

    assert observation.observation_id == "observation-policy-quality-v1"
    assert observation.evaluation_id == "eval-policy-quality"
    assert observation.observed_score == 0.7
    assert observation.observed_pass_count == 7
    assert observation.observed_fail_count == 3
    assert service.get_observation(observation.observation_id) == observation
    assert service.list_observations() == [observation]


def test_duplicate_baselines_and_observations_are_rejected(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_baseline(baseline_request("baseline-duplicate"))

    try:
        service.register_baseline(baseline_request("baseline-duplicate"))
    except EvaluationDriftBaselineAlreadyExistsError as exc:
        assert str(exc) == (
            "Evaluation drift baseline already registered: baseline-duplicate"
        )
    else:
        raise AssertionError("duplicate baseline was not rejected")

    service.register_observation(
        observation_request("observation-duplicate")
    )
    try:
        service.register_observation(
            observation_request("observation-duplicate")
        )
    except EvaluationDriftObservationAlreadyExistsError as exc:
        assert str(exc) == (
            "Evaluation drift observation already registered: "
            "observation-duplicate"
        )
    else:
        raise AssertionError("duplicate observation was not rejected")


def test_projection_calculates_drift_statuses_and_latest_baseline(
    tmp_path,
) -> None:
    service = make_service(tmp_path)
    service.register_baseline(baseline_request("baseline-old", score=0.5))
    service.register_baseline(baseline_request("baseline-latest", score=0.8))
    service.register_observation(
        observation_request("observation-regressed", score=0.7)
    )
    service.register_observation(
        observation_request("observation-improved", score=0.9)
    )
    service.register_observation(
        observation_request("observation-unchanged", score=0.8)
    )
    service.register_observation(
        EvaluationDriftObservationCreate(
            observation_id="observation-missing-baseline",
            evaluation_id="eval-without-baseline",
            evaluation_name="Unbaselined evaluation",
            evaluation_version=1,
            observed_score=0.1,
            observed_pass_count=1,
            observed_fail_count=9,
        )
    )
    builder = EvaluationDriftProjectionBuilderService(
        drift=service,
        clock=lambda: GENERATED_AT,
    )

    first = builder.build().model_dump(mode="json")
    second = builder.build().model_dump(mode="json")

    assert first == second
    assert first["metadata"]["projection_type"] == EVALUATION_DRIFT_PROJECTION_TYPE
    assert first["metadata"]["builder_name"] == (
        "EvaluationDriftProjectionBuilderService"
    )
    assert first["metadata"]["reconstruction"] == {
        "projection_type": EVALUATION_DRIFT_PROJECTION_TYPE,
        "reconstruction_source": "runtime_event_store",
        "rebuildable": True,
        "authoritative_source": "runtime_event_store",
    }
    assert first["total_baselines"] == 2
    assert first["total_observations"] == 4
    assert first["total_drift_records"] == 3
    assert first["regressed_count"] == 1
    assert first["improved_count"] == 1
    assert first["unchanged_count"] == 1

    records = {
        record["drift_id"]: record
        for record in first["drift_records"]
    }
    assert records["drift-observation-regressed"]["drift_status"] == "regressed"
    assert records["drift-observation-regressed"]["baseline_score"] == 0.8
    assert records["drift-observation-regressed"]["score_delta"] == pytest.approx(
        -0.1
    )
    assert records["drift-observation-improved"]["drift_status"] == "improved"
    assert records["drift-observation-improved"]["score_delta"] == pytest.approx(
        0.1
    )
    assert records["drift-observation-unchanged"]["drift_status"] == "unchanged"
    assert records["drift-observation-unchanged"]["score_delta"] == 0.0
    assert "drift-observation-missing-baseline" not in records


def test_empty_projection_has_no_drift_records(tmp_path) -> None:
    builder = EvaluationDriftProjectionBuilderService(
        drift=make_service(tmp_path),
        clock=lambda: GENERATED_AT,
    )

    projection = builder.build()

    assert projection.total_baselines == 0
    assert projection.total_observations == 0
    assert projection.total_drift_records == 0
    assert projection.regressed_count == 0
    assert projection.improved_count == 0
    assert projection.unchanged_count == 0
    assert projection.drift_records == []


def test_evaluation_drift_routes_work() -> None:
    client = TestClient(app)

    baseline_response = client.post(
        "/evaluation-drift/baselines",
        json={
            "baseline_id": "baseline-route",
            "evaluation_id": "eval-route",
            "evaluation_name": "Route evaluation",
            "evaluation_version": 1,
            "baseline_score": 0.75,
            "baseline_pass_count": 3,
            "baseline_fail_count": 1,
        },
    )
    assert baseline_response.status_code == 200

    observation_response = client.post(
        "/evaluation-drift/observations",
        json={
            "observation_id": "observation-route",
            "evaluation_id": "eval-route",
            "evaluation_name": "Route evaluation",
            "evaluation_version": 1,
            "observed_score": 0.5,
            "observed_pass_count": 2,
            "observed_fail_count": 2,
        },
    )
    assert observation_response.status_code == 200

    baselines = client.get("/evaluation-drift/baselines")
    observations = client.get("/evaluation-drift/observations")
    projection = client.get("/evaluation-drift/projection")
    duplicate = client.post(
        "/evaluation-drift/baselines",
        json={
            "baseline_id": "baseline-route",
            "evaluation_id": "eval-route",
            "evaluation_name": "Route evaluation",
            "evaluation_version": 1,
            "baseline_score": 0.75,
            "baseline_pass_count": 3,
            "baseline_fail_count": 1,
        },
    )

    assert baselines.status_code == 200
    assert observations.status_code == 200
    assert projection.status_code == 200
    assert duplicate.status_code == 409
    assert baselines.json()[0]["baseline_id"] == "baseline-route"
    assert observations.json()[0]["observation_id"] == "observation-route"
    assert projection.json()["total_drift_records"] == 1
    assert projection.json()["regressed_count"] == 1


def test_projection_registry_diagnostics_and_query_executor_visibility() -> None:
    client = TestClient(app)

    runtime_response = client.get("/runtime/projections")
    diagnostics_response = client.get("/runtime/projection-diagnostics")
    contract_response = client.get(
        "/runtime/projections/registry/evaluation_drift"
    )
    query_response = client.post(
        "/runtime/query-execute",
        json={"query_id": "evaluation_drift"},
    )
    direct_query = query_executor_service.execute(
        QueryExecutionRequest(query_id="runtime.evaluation_drift")
    )

    assert runtime_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert contract_response.status_code == 200
    assert query_response.status_code == 200
    assert EVALUATION_DRIFT_PROJECTION_TYPE in (
        runtime_response.json()["projection_types"]
    )
    assert EVALUATION_DRIFT_PROJECTION_TYPE in (
        diagnostics_response.json()["projection_types"]
    )
    assert contract_response.json()["projection_name"] == (
        EVALUATION_DRIFT_PROJECTION_TYPE
    )
    assert contract_response.json()["route"] == "/evaluation-drift/projection"
    assert contract_response.json()["capabilities"]["reconstructable"] is True
    assert query_response.json()["projection_type"] == (
        EVALUATION_DRIFT_PROJECTION_TYPE
    )
    assert query_response.json()["result"]["total_drift_records"] == 0
    assert direct_query.projection_type == EVALUATION_DRIFT_PROJECTION_TYPE
