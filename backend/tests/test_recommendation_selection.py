import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.routes import runtime as runtime_routes
from app.services.event_service import event_service
from app.services.planner_recommendation_service import (
    planner_recommendation_service,
)
from app.services.proposal_service import proposal_service
from app.services.recommendation_selection_service import (
    RecommendationSelectionService,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service


class FakeRecommendationService:
    def __init__(self, records) -> None:
        self.records = records

    def list_recommendations(
        self,
        session_id: str | None = None,
        status: str | None = None,
    ):
        return [
            record
            for record in self.records
            if (session_id is None or record.session_id == session_id)
            and (status is None or record.status == status)
        ]

    def proposed_tool_for(self, record):
        return record.proposed_tool


def recommendation(
    recommendation_id: str,
    *,
    status: str = "active",
    governance_status: str = "ok",
    confidence: float = 0.5,
    created_at: datetime | None = None,
    session_id: str = "session-1",
):
    return SimpleNamespace(
        id=recommendation_id,
        session_id=session_id,
        status=status,
        governance_status=governance_status,
        confidence=confidence,
        created_at=created_at or datetime(2026, 6, 6, tzinfo=UTC),
        proposed_tool={"id": f"tool-{recommendation_id}"},
    )


def selection_service(records) -> RecommendationSelectionService:
    return RecommendationSelectionService(FakeRecommendationService(records))


def test_selection_only_ranks_active_recommendations() -> None:
    preview = selection_service(
        [
            recommendation("active"),
            recommendation("promoted", status="promoted", confidence=1.0),
            recommendation("dismissed", status="dismissed", confidence=1.0),
            recommendation("other-session", session_id="session-2"),
        ]
    ).preview("session-1")

    assert [item.recommendation_id for item in preview.ranked_recommendations] == [
        "active"
    ]


def test_selection_prefers_governance_status_before_confidence() -> None:
    preview = selection_service(
        [
            recommendation("critical", governance_status="critical", confidence=1.0),
            recommendation("degraded", governance_status="degraded", confidence=0.9),
            recommendation("ok", governance_status="ok", confidence=0.1),
        ]
    ).preview("session-1")

    assert [item.recommendation_id for item in preview.ranked_recommendations] == [
        "ok",
        "degraded",
        "critical",
    ]


def test_selection_prefers_higher_confidence_with_same_governance() -> None:
    preview = selection_service(
        [
            recommendation("lower", confidence=0.4),
            recommendation("higher", confidence=0.8),
        ]
    ).preview("session-1")

    assert preview.selected_recommendation_id == "higher"


def test_selection_uses_newer_creation_then_id_as_stable_tiebreakers() -> None:
    created_at = datetime(2026, 6, 6, tzinfo=UTC)
    preview = selection_service(
        [
            recommendation("z-id", created_at=created_at),
            recommendation("a-id", created_at=created_at),
            recommendation("newer", created_at=created_at + timedelta(seconds=1)),
        ]
    ).preview("session-1")

    assert [item.recommendation_id for item in preview.ranked_recommendations] == [
        "newer",
        "a-id",
        "z-id",
    ]
    assert [item.rank for item in preview.ranked_recommendations] == [1, 2, 3]


def test_selection_returns_no_selection_for_empty_active_set() -> None:
    preview = selection_service(
        [recommendation("dismissed", status="dismissed")]
    ).preview("session-1")

    assert preview.selected_recommendation_id is None
    assert preview.selected_proposed_tool is None
    assert preview.selection_reason == "no_active_recommendations"
    assert preview.ranked_recommendations == []


def planner_tool() -> Tool:
    return Tool(
        id="selection-tool",
        name="shell.read",
        description="Read only",
        enabled=True,
        created_at="2026-06-06T00:00:00+00:00",
        updated_at="2026-06-06T00:00:00+00:00",
        parameters=[],
    )


def create_stored_recommendation(
    session_id: str,
    task_id: str,
    objective: str,
    governance_status: str,
    confidence: float,
):
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
            confidence=confidence,
        ),
        {"governance_status": governance_status},
    )


def test_selection_preview_endpoint_is_read_only(monkeypatch) -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("selection-task")
    selected = create_stored_recommendation(
        session.id,
        session.task_id,
        "Selected",
        "ok",
        0.8,
    )
    excluded_promoted = create_stored_recommendation(
        session.id,
        session.task_id,
        "Promoted",
        "ok",
        1.0,
    )
    excluded_dismissed = create_stored_recommendation(
        session.id,
        session.task_id,
        "Dismissed",
        "ok",
        1.0,
    )
    planner_recommendation_service.mark_promoted(excluded_promoted.id)
    asyncio.run(planner_recommendation_service.dismiss(excluded_dismissed.id))

    async def fail(*args, **kwargs):
        raise AssertionError("selection preview must remain read-only")

    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail)
    monkeypatch.setattr(runtime_routes.work_loop_service, "run_single_step", fail)
    monkeypatch.setattr(tool_execution_service, "execute_invocation", fail)
    monkeypatch.setattr(runtime_routes.python_async_runtime, "run_task", fail)

    statuses_before = {
        record.id: record.status
        for record in planner_recommendation_service.list_recommendations(
            session.id
        )
    }
    event_count_before = len(event_service.list_persisted_events())

    response = client.get(
        f"/runtime/sessions/{session.id}/planner-recommendations/"
        "selection-preview"
    )

    statuses_after = {
        record.id: record.status
        for record in planner_recommendation_service.list_recommendations(
            session.id
        )
    }
    assert response.status_code == 200
    assert response.json()["selected_recommendation_id"] == selected.id
    assert response.json()["selected_proposed_tool"]["id"] == "selection-tool"
    assert [
        item["recommendation_id"]
        for item in response.json()["ranked_recommendations"]
    ] == [selected.id]
    assert statuses_after == statuses_before
    assert len(event_service.list_persisted_events()) == event_count_before
    assert proposal_service.list_proposals(task_id=session.task_id) == []
    assert tool_invocation_service.list_invocations(session_id=session.id) == []


def test_selection_preview_endpoint_handles_empty_and_missing_sessions() -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("empty-selection-task")

    empty_response = client.get(
        f"/runtime/sessions/{session.id}/planner-recommendations/"
        "selection-preview"
    )
    missing_response = client.get(
        "/runtime/sessions/missing/planner-recommendations/selection-preview"
    )

    assert empty_response.status_code == 200
    assert empty_response.json()["selected_recommendation_id"] is None
    assert empty_response.json()["ranked_recommendations"] == []
    assert missing_response.status_code == 404
