from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.decision_record import DecisionType
from app.models.evaluation_record import EvaluationRecordCreate
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.query_executor import QueryExecutionRequest
from app.models.tool import Tool
from app.runtime.projection_registry import projection_registry
from app.services.decision_record_service import decision_record_service
from app.services.evaluation_record_service import evaluation_record_service
from app.services.governance_health_rollup_projection_builder_service import (
    GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE,
    GovernanceHealthRollupProjectionBuilderService,
)
from app.services.planner_recommendation_service import (
    planner_recommendation_service,
)
from app.services.policy_service import policy_service
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_executor_service import QueryExecutorService
from app.services.runtime_session_service import runtime_session_service


GENERATED_AT = datetime(2026, 6, 20, 14, 0, tzinfo=UTC)


def planner_tool() -> Tool:
    return Tool(
        id="governance-health-tool",
        name="governance.health",
        description="Governance health test tool",
        enabled=True,
        created_at="2026-06-20T00:00:00+00:00",
        updated_at="2026-06-20T00:00:00+00:00",
        parameters=[],
    )


def create_recommendation(session_id: str, task_id: str, objective: str):
    return planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective=objective,
            available_tools=[planner_tool()],
        ),
        PlannerResponse(
            proposed_tool=planner_tool(),
            rationale=f"Recommend {objective}",
            confidence=0.8,
        ),
        {"governance_status": "ok"},
    )


def create_decision(session_id: str, task_id: str, objective: str):
    recommendation = create_recommendation(session_id, task_id, objective)
    return decision_record_service.create_decision_record(
        session_id,
        DecisionType.RECOMMENDATION_SELECTION,
        recommendation.id,
        f"Select {objective}",
    )


def create_evaluation(
    *,
    target_type: str,
    target_id: str,
    outcome: str,
    score: float | None = None,
) -> str:
    record = evaluation_record_service.create_record(
        EvaluationRecordCreate(
            target_type=target_type,
            target_id=target_id,
            evaluation_type="outcome",
            outcome=outcome,
            score=score,
            evaluator="test-suite",
        )
    )
    return record.evaluation_id


def build_rollup():
    return GovernanceHealthRollupProjectionBuilderService(
        clock=lambda: GENERATED_AT
    ).build()


def test_governance_health_rollup_empty_state_is_unknown() -> None:
    rollup = build_rollup()

    assert rollup.total_evaluations == 0
    assert rollup.overall_success_rate == 0.0
    assert rollup.overall_failure_rate == 0.0
    assert rollup.overall_rejection_rate == 0.0
    assert rollup.overall_reversion_rate == 0.0
    assert rollup.average_evaluation_score is None
    assert rollup.recommendation_success_rate == 0.0
    assert rollup.decision_success_rate == 0.0
    assert rollup.decision_evaluation_coverage_rate == 0.0
    assert rollup.policy_success_rate == 0.0
    assert rollup.health_status == "unknown"
    assert rollup.health_reasons == ["no_evaluation_data"]
    assert rollup.generated_at == GENERATED_AT

    response = TestClient(app).get("/runtime/governance-health-rollup")

    assert response.status_code == 200
    assert response.json()["health_status"] == "unknown"


def test_governance_health_rollup_healthy_status_and_rates() -> None:
    session = runtime_session_service.create_session("healthy-governance")
    first_decision = create_decision(session.id, session.task_id, "first")
    uncovered_decision = create_decision(
        session.id,
        session.task_id,
        "uncovered",
    )
    recommendation = create_recommendation(
        session.id,
        session.task_id,
        "recommendation",
    )
    policy = policy_service.create_policy(
        name="Healthy policy",
        description="Policy linked to healthy evaluation.",
        policy_type="governance",
        status="active",
    )
    policy_version = policy_service.add_policy_version(
        policy.id,
        version=1,
        rule_payload={"rule": "healthy"},
    )

    decision_success = create_evaluation(
        target_type="decision",
        target_id=first_decision.decision_id,
        outcome="success",
        score=1.0,
    )
    create_evaluation(
        target_type="decision",
        target_id=first_decision.decision_id,
        outcome="success",
        score=0.8,
    )
    create_evaluation(
        target_type="recommendation",
        target_id=recommendation.id,
        outcome="success",
        score=0.9,
    )
    create_evaluation(
        target_type="artifact",
        target_id="artifact-1",
        outcome="success",
        score=0.7,
    )
    create_evaluation(
        target_type="runtime_session",
        target_id=session.id,
        outcome="failure",
        score=0.2,
    )
    policy_service.record_policy_decision(
        policy.id,
        policy_version.id,
        target_type="decision",
        target_id=first_decision.decision_id,
        decision="allow",
        reason="Linked to successful evaluation.",
        evaluation_id=decision_success,
    )

    rollup = build_rollup()
    second = build_rollup()

    assert rollup.model_dump(mode="json") == second.model_dump(mode="json")
    assert uncovered_decision.decision_id
    assert rollup.total_evaluations == 5
    assert rollup.overall_success_rate == 4 / 5
    assert rollup.overall_failure_rate == 1 / 5
    assert rollup.overall_rejection_rate == 0.0
    assert rollup.overall_reversion_rate == 0.0
    assert rollup.average_evaluation_score == pytest.approx(0.72)
    assert rollup.recommendation_success_rate == 1.0
    assert rollup.decision_success_rate == 1.0
    assert rollup.decision_evaluation_coverage_rate == 0.5
    assert rollup.policy_success_rate == 1.0
    assert rollup.health_status == "healthy"
    assert rollup.health_reasons == [
        "overall_success_rate_at_least_0.8",
        "overall_reversion_rate_at_most_0.05",
    ]


def test_governance_health_rollup_watch_and_degraded_statuses() -> None:
    create_evaluation(
        target_type="artifact",
        target_id="watch-1",
        outcome="success",
    )
    create_evaluation(
        target_type="artifact",
        target_id="watch-2",
        outcome="success",
    )
    create_evaluation(
        target_type="artifact",
        target_id="watch-3",
        outcome="success",
    )
    create_evaluation(
        target_type="artifact",
        target_id="watch-4",
        outcome="failure",
    )
    create_evaluation(
        target_type="artifact",
        target_id="watch-5",
        outcome="reverted",
    )

    watch = build_rollup()

    assert watch.overall_success_rate == 3 / 5
    assert watch.overall_reversion_rate == 1 / 5
    assert watch.health_status == "watch"
    assert watch.health_reasons == [
        "overall_success_rate_at_least_0.6",
        "healthy_threshold_not_met",
    ]

    evaluation_record_service.reset()
    create_evaluation(
        target_type="artifact",
        target_id="degraded-1",
        outcome="success",
    )
    create_evaluation(
        target_type="artifact",
        target_id="degraded-2",
        outcome="failure",
    )
    create_evaluation(
        target_type="artifact",
        target_id="degraded-3",
        outcome="rejected",
    )

    degraded = build_rollup()

    assert degraded.overall_success_rate == 1 / 3
    assert degraded.overall_failure_rate == 1 / 3
    assert degraded.overall_rejection_rate == 1 / 3
    assert degraded.health_status == "degraded"
    assert degraded.health_reasons == ["overall_success_rate_below_0.6"]


def test_governance_health_rollup_is_registered_and_queryable() -> None:
    assert GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )

    catalog_entries = {
        entry.projection_type: entry
        for entry in QueryCatalogService().get_catalog().entries
    }
    assert catalog_entries[GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE].route == (
        "/runtime/governance-health-rollup"
    )
    assert catalog_entries[GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE].category == (
        "governance"
    )

    result = QueryExecutorService().execute(
        QueryExecutionRequest(query_id=GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE)
    )

    assert result.query_id == "runtime.governance_health_rollup"
    assert result.projection_type == GOVERNANCE_HEALTH_ROLLUP_PROJECTION_TYPE
    assert result.route == "/runtime/governance-health-rollup"
    assert result.result.health_status == "unknown"
