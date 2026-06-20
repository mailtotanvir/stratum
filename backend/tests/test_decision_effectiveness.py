from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.decision_record import DecisionType
from app.models.evaluation_record import EvaluationRecordCreate
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.query_executor import QueryExecutionRequest
from app.models.tool import Tool
from app.runtime.projection_registry import projection_registry
from app.services.decision_effectiveness_projection_builder_service import (
    DECISION_EFFECTIVENESS_PROJECTION_TYPE,
    DecisionEffectivenessProjectionBuilderService,
)
from app.services.decision_record_service import decision_record_service
from app.services.evaluation_record_service import evaluation_record_service
from app.services.planner_recommendation_service import (
    planner_recommendation_service,
)
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_executor_service import QueryExecutorService
from app.services.runtime_session_service import runtime_session_service


GENERATED_AT = datetime(2026, 6, 20, 13, 0, tzinfo=UTC)


def planner_tool(
    tool_id: str = "decision-tool",
    name: str = "decision.tool",
) -> Tool:
    return Tool(
        id=tool_id,
        name=name,
        description="Decision test tool",
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
    decision_id: str,
    outcome: str,
    score: float | None = None,
) -> None:
    evaluation_record_service.create_record(
        EvaluationRecordCreate(
            target_type="decision",
            target_id=decision_id,
            evaluation_type="outcome",
            outcome=outcome,
            score=score,
            evaluator="test-suite",
        )
    )


def build_projection():
    return DecisionEffectivenessProjectionBuilderService(
        clock=lambda: GENERATED_AT
    ).build()


def projections_by_id():
    return {
        projection.decision_id: projection
        for projection in build_projection()
    }


def test_decision_effectiveness_builds_deterministically() -> None:
    session = runtime_session_service.create_session("decision-effectiveness")
    successful = create_decision(session.id, session.task_id, "successful")
    failed = create_decision(session.id, session.task_id, "failed")
    uncovered = create_decision(session.id, session.task_id, "uncovered")

    create_evaluation(successful.decision_id, "success", 0.9)
    create_evaluation(successful.decision_id, "accepted", None)
    create_evaluation(successful.decision_id, "failure", 0.3)
    create_evaluation(failed.decision_id, "rejected", 0.1)
    create_evaluation(failed.decision_id, "reverted", None)
    create_evaluation(failed.decision_id, "inconclusive", 0.4)
    create_evaluation("missing-decision", "success", 1.0)

    first = [
        projection.model_dump(mode="json")
        for projection in build_projection()
    ]
    second = [
        projection.model_dump(mode="json")
        for projection in build_projection()
    ]

    assert first == second

    projections = projections_by_id()
    assert set(projections) == {
        successful.decision_id,
        failed.decision_id,
        uncovered.decision_id,
    }

    successful_projection = projections[successful.decision_id]
    assert successful_projection.decision_type == "recommendation_selection"
    assert successful_projection.session_id == session.id
    assert successful_projection.task_id == session.task_id
    assert successful_projection.evaluation_count == 3
    assert successful_projection.success_count == 1
    assert successful_projection.failure_count == 1
    assert successful_projection.accepted_count == 1
    assert successful_projection.rejected_count == 0
    assert successful_projection.reverted_count == 0
    assert successful_projection.inconclusive_count == 0
    assert successful_projection.success_rate == 1 / 3
    assert successful_projection.failure_rate == 1 / 3
    assert successful_projection.average_score == 0.6
    assert successful_projection.has_evaluation_coverage is True
    assert successful_projection.generated_at == GENERATED_AT

    failed_projection = projections[failed.decision_id]
    assert failed_projection.evaluation_count == 3
    assert failed_projection.success_count == 0
    assert failed_projection.failure_count == 0
    assert failed_projection.rejected_count == 1
    assert failed_projection.reverted_count == 1
    assert failed_projection.inconclusive_count == 1
    assert failed_projection.success_rate == 0.0
    assert failed_projection.failure_rate == 0.0
    assert failed_projection.average_score == 0.25
    assert failed_projection.has_evaluation_coverage is True

    uncovered_projection = projections[uncovered.decision_id]
    assert uncovered_projection.evaluation_count == 0
    assert uncovered_projection.success_count == 0
    assert uncovered_projection.failure_count == 0
    assert uncovered_projection.success_rate == 0.0
    assert uncovered_projection.failure_rate == 0.0
    assert uncovered_projection.average_score is None
    assert uncovered_projection.has_evaluation_coverage is False


def test_decision_effectiveness_empty_state() -> None:
    assert build_projection() == []

    response = TestClient(app).get("/runtime/decision-effectiveness")

    assert response.status_code == 200
    assert response.json() == []


def test_decision_effectiveness_projection_is_registered_and_queryable() -> None:
    assert DECISION_EFFECTIVENESS_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )

    catalog_entries = {
        entry.projection_type: entry
        for entry in QueryCatalogService().get_catalog().entries
    }
    assert catalog_entries[DECISION_EFFECTIVENESS_PROJECTION_TYPE].route == (
        "/runtime/decision-effectiveness"
    )
    assert catalog_entries[DECISION_EFFECTIVENESS_PROJECTION_TYPE].category == (
        "decisions"
    )

    result = QueryExecutorService().execute(
        QueryExecutionRequest(query_id=DECISION_EFFECTIVENESS_PROJECTION_TYPE)
    )

    assert result.query_id == "runtime.decision_effectiveness"
    assert result.projection_type == DECISION_EFFECTIVENESS_PROJECTION_TYPE
    assert result.route == "/runtime/decision-effectiveness"
    assert result.result == []
