from datetime import UTC, datetime

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
from app.services.planner_recommendation_service import (
    planner_recommendation_service,
)
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_executor_service import QueryExecutorService
from app.services.recommendation_outcome_projection_builder_service import (
    RECOMMENDATION_OUTCOME_PROJECTION_TYPE,
    RecommendationOutcomeProjectionBuilderService,
)
from app.services.runtime_session_service import runtime_session_service


GENERATED_AT = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def planner_tool(
    tool_id: str = "shell-read",
    name: str = "shell.read",
) -> Tool:
    return Tool(
        id=tool_id,
        name=name,
        description="Read shell state",
        enabled=True,
        created_at="2026-06-20T00:00:00+00:00",
        updated_at="2026-06-20T00:00:00+00:00",
        parameters=[],
    )


def create_recommendation(
    *,
    session_id: str,
    task_id: str,
    objective: str,
    confidence: float = 0.8,
    tool: Tool | None = None,
):
    return planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective=objective,
            available_tools=[planner_tool()],
        ),
        PlannerResponse(
            proposed_tool=tool,
            rationale=f"Recommend {objective}",
            confidence=confidence,
        ),
        {"governance_status": "ok"},
    )


def create_evaluation(
    recommendation_id: str,
    outcome: str,
    score: float | None = None,
) -> None:
    evaluation_record_service.create_record(
        EvaluationRecordCreate(
            target_type="recommendation",
            target_id=recommendation_id,
            evaluation_type="outcome",
            outcome=outcome,
            score=score,
            evaluator="test-suite",
        )
    )


def build_projection():
    builder = RecommendationOutcomeProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    return builder.build()


def projections_by_id():
    return {
        projection.recommendation_id: projection
        for projection in build_projection()
    }


def test_recommendation_outcomes_build_deterministically() -> None:
    session = runtime_session_service.create_session("recommendation-task")
    selected = create_recommendation(
        session_id=session.id,
        task_id=session.task_id,
        objective="Selected recommendation",
        tool=planner_tool(),
    )
    not_selected = create_recommendation(
        session_id=session.id,
        task_id=session.task_id,
        objective="Rejected recommendation",
        tool=planner_tool("code-format", "code.format"),
    )
    promoted_without_decision = create_recommendation(
        session_id=session.id,
        task_id=session.task_id,
        objective="Promoted without decision",
        tool=None,
    )
    planner_recommendation_service.mark_promoted(promoted_without_decision.id)

    for _ in range(2):
        decision_record_service.create_decision_record(
            session.id,
            DecisionType.RECOMMENDATION_SELECTION,
            selected.id,
            "Selected by operator",
        )

    create_evaluation(selected.id, "success", 0.8)
    create_evaluation(selected.id, "failure", 0.2)
    create_evaluation(selected.id, "accepted", None)
    create_evaluation(not_selected.id, "rejected", 0.1)
    create_evaluation(not_selected.id, "reverted", None)
    create_evaluation(not_selected.id, "inconclusive", 0.4)
    create_evaluation("missing-recommendation", "success", 1.0)

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
        selected.id,
        not_selected.id,
        promoted_without_decision.id,
    }

    selected_projection = projections[selected.id]
    assert selected_projection.recommendation_type == "shell.read"
    assert selected_projection.recommendation_category == "shell"
    assert selected_projection.selected_count == 2
    assert selected_projection.not_selected_count == 0
    assert selected_projection.evaluation_count == 3
    assert selected_projection.success_count == 1
    assert selected_projection.failure_count == 1
    assert selected_projection.accepted_count == 1
    assert selected_projection.rejected_count == 0
    assert selected_projection.reverted_count == 0
    assert selected_projection.inconclusive_count == 0
    assert selected_projection.success_rate == 1 / 3
    assert selected_projection.average_score == 0.5
    assert selected_projection.generated_at == GENERATED_AT

    not_selected_projection = projections[not_selected.id]
    assert not_selected_projection.recommendation_type == "code.format"
    assert not_selected_projection.recommendation_category == "code"
    assert not_selected_projection.selected_count == 0
    assert not_selected_projection.not_selected_count == 1
    assert not_selected_projection.evaluation_count == 3
    assert not_selected_projection.success_count == 0
    assert not_selected_projection.rejected_count == 1
    assert not_selected_projection.reverted_count == 1
    assert not_selected_projection.inconclusive_count == 1
    assert not_selected_projection.success_rate == 0.0
    assert not_selected_projection.average_score == 0.25

    promoted_projection = projections[promoted_without_decision.id]
    assert promoted_projection.recommendation_type == "no_tool"
    assert promoted_projection.recommendation_category == "uncategorized"
    assert promoted_projection.selected_count == 1
    assert promoted_projection.not_selected_count == 0
    assert promoted_projection.evaluation_count == 0
    assert promoted_projection.success_rate == 0.0
    assert promoted_projection.average_score is None


def test_recommendation_outcomes_empty_state() -> None:
    assert build_projection() == []

    response = TestClient(app).get("/runtime/recommendation-outcomes")

    assert response.status_code == 200
    assert response.json() == []


def test_recommendation_outcome_projection_is_registered_and_discoverable() -> None:
    assert RECOMMENDATION_OUTCOME_PROJECTION_TYPE in (
        projection_registry.list_projection_types()
    )

    catalog_entries = {
        entry.projection_type: entry
        for entry in QueryCatalogService().get_catalog().entries
    }
    assert catalog_entries[RECOMMENDATION_OUTCOME_PROJECTION_TYPE].route == (
        "/runtime/recommendation-outcomes"
    )
    assert (
        catalog_entries[RECOMMENDATION_OUTCOME_PROJECTION_TYPE].category
        == "recommendations"
    )

    result = QueryExecutorService().execute(
        QueryExecutionRequest(query_id=RECOMMENDATION_OUTCOME_PROJECTION_TYPE)
    )

    assert result.query_id == "runtime.recommendation_outcome"
    assert result.projection_type == RECOMMENDATION_OUTCOME_PROJECTION_TYPE
    assert result.route == "/runtime/recommendation-outcomes"
    assert result.result == []
