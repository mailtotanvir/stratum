from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.evaluation_accountability import EvaluationScenarioCreate, EvaluationRunCreate
from app.services.evaluation_accountability_service import (
    EvaluationScenarioAlreadyExistsError,
    EvaluationAccountabilityService,
)
from app.services.event_service import EventService
from app.services.trace_service import TraceService


def make_service(tmp_path) -> EvaluationAccountabilityService:
    return EvaluationAccountabilityService(
        events=EventService(TraceService(tmp_path / "evaluation-accountability.db"))
    )


def scenario_request() -> EvaluationScenarioCreate:
    return EvaluationScenarioCreate(
        scenario_id="scenario-provider-quality",
        title="Provider quality",
        purpose="Check deterministic provider execution quality.",
        input_fixture="fixtures/provider-quality.json",
        expected_behavior="Stable answer and traceable evidence.",
        rubric="Pass if score >= 0.8 and evidence exists.",
        target_type="provider_execution",
        version=1,
        tags=["provider", "regression"],
        risk_level="medium",
    )


def test_scenario_registration_and_run_projection(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_scenario(scenario_request())
    run = service.record_run(
        EvaluationRunCreate(
            scenario_id="scenario-provider-quality",
            target_type="provider_execution",
            target_id="provider-openai:gpt-4o",
            target_runtime_event_id=12,
            evaluator="human",
            evaluator_type="operator",
            outcome="pass",
            score=0.9,
            evidence=[{"kind": "trace", "ref": "runtime-event-12"}],
            metadata={"provider_id": "openai"},
        )
    )

    projection = service.build_projection()
    assert run.run_id == "evaluation-run-1"
    assert projection.scenarios[0].scenario_id == "scenario-provider-quality"
    assert projection.runs[0].target_id == "provider-openai:gpt-4o"
    assert projection.scorecards[0].evaluation_count == 1
    assert projection.regressions.comparison_count == 0


def test_duplicate_scenarios_are_rejected(tmp_path) -> None:
    service = make_service(tmp_path)
    service.register_scenario(scenario_request())
    try:
        service.register_scenario(scenario_request())
    except EvaluationScenarioAlreadyExistsError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate scenario was not rejected")


def test_evaluation_accountability_routes_work() -> None:
    client = TestClient(app)

    response = client.post(
        "/evaluation-accountability/scenarios",
        json={
            "scenario_id": "scenario-route",
            "title": "Route scenario",
            "purpose": "Route verification.",
            "input_fixture": "fixtures/route.json",
            "expected_behavior": "Deterministic output.",
            "rubric": "Pass if evidence is present.",
            "target_type": "runtime_session",
            "version": 1,
            "tags": ["route"],
            "risk_level": "low",
        },
    )
    assert response.status_code == 200

    run_response = client.post(
        "/evaluation-accountability/runs",
        json={
            "scenario_id": "scenario-route",
            "target_type": "runtime_session",
            "target_id": "session-1",
            "target_runtime_event_id": 7,
            "evaluator": "human",
            "evaluator_type": "operator",
            "outcome": "review",
            "score": 0.5,
            "evidence": [],
            "metadata": {},
        },
    )
    assert run_response.status_code == 200

    projection = client.get("/evaluation-accountability/projection")
    assert projection.status_code == 200
    assert projection.json()["scenarios"][0]["scenario_id"] == "scenario-route"
