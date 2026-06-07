from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.routes import runtime as runtime_routes
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.proposal_service import ProposalService, proposal_service
from app.services.reconstruction_service import ReconstructionService
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.task_service import TaskService
from app.services.trace_service import TraceService


def decision_tool() -> Tool:
    return Tool(
        id="decision-tool",
        name="shell.read",
        description="Read only",
        enabled=True,
        created_at="2026-06-07T00:00:00+00:00",
        updated_at="2026-06-07T00:00:00+00:00",
        parameters=[],
    )


def create_recommendation(session_id: str, task_id: str):
    return planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective="Inspect deterministic state",
            available_tools=[decision_tool()],
        ),
        PlannerResponse(
            proposed_tool=decision_tool(),
            rationale="Read the current state",
            confidence=0.9,
        ),
        {"governance_status": "ok"},
    )


def test_decision_record_creation_is_audit_only(monkeypatch) -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("decision-task")
    recommendation = create_recommendation(session.id, session.task_id)

    async def fail(*args, **kwargs):
        raise AssertionError("decision recording must not invoke runtime behavior")

    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail)
    monkeypatch.setattr(runtime_routes.work_loop_service, "run_single_step", fail)
    monkeypatch.setattr(tool_execution_service, "execute_invocation", fail)
    monkeypatch.setattr(runtime_routes.python_async_runtime, "run_task", fail)

    proposal_count_before = len(
        proposal_service.list_proposals(task_id=session.task_id)
    )
    invocation_count_before = len(
        tool_invocation_service.list_invocations(session_id=session.id)
    )
    execution_state_before = runtime_routes.runtime_execution_service.list()

    response = client.post(
        f"/runtime/sessions/{session.id}/decision-records",
        json={
            "decision_type": "recommendation_selection",
            "selected_entity_id": recommendation.id,
            "rationale": "Highest-ranked eligible recommendation",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.id
    assert body["task_id"] == session.task_id
    assert body["decision_type"] == "recommendation_selection"
    assert body["selected_entity_id"] == recommendation.id
    assert body["selected_entity_type"] == "planner_recommendation"
    assert body["rationale"] == "Highest-ranked eligible recommendation"
    assert decision_record_service.get_decision_record(
        body["decision_id"]
    ).decision_id == body["decision_id"]

    events = event_service.list_persisted_events(
        event_type="decision_record_created"
    )
    assert len(events) == 1
    assert events[0].metadata["decision_id"] == body["decision_id"]
    assert events[0].metadata["decision_type"] == "recommendation_selection"
    assert events[0].metadata["selected_entity_id"] == recommendation.id
    assert events[0].metadata["selected_entity_type"] == "planner_recommendation"
    assert events[0].metadata["session_id"] == session.id

    assert len(proposal_service.list_proposals(task_id=session.task_id)) == (
        proposal_count_before
    )
    assert len(tool_invocation_service.list_invocations(session_id=session.id)) == (
        invocation_count_before
    )
    assert runtime_routes.runtime_execution_service.list() == (
        execution_state_before
    )


def test_decision_record_listing_is_session_scoped_and_ordered() -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("decision-list-task")
    other_session = runtime_session_service.create_session("other-decision-task")
    recommendation = create_recommendation(session.id, session.task_id)
    other_recommendation = create_recommendation(
        other_session.id,
        other_session.task_id,
    )

    first = client.post(
        f"/runtime/sessions/{session.id}/decision-records",
        json={
            "decision_type": "recommendation_selection",
            "selected_entity_id": recommendation.id,
            "rationale": "First",
        },
    ).json()
    second = client.post(
        f"/runtime/sessions/{session.id}/decision-records",
        json={
            "decision_type": "recommendation_selection",
            "selected_entity_id": recommendation.id,
            "rationale": "Second",
        },
    ).json()
    client.post(
        f"/runtime/sessions/{other_session.id}/decision-records",
        json={
            "decision_type": "recommendation_selection",
            "selected_entity_id": other_recommendation.id,
            "rationale": "Other",
        },
    )

    response = client.get(
        f"/runtime/sessions/{session.id}/decision-records"
    )

    assert response.status_code == 200
    assert [record["decision_id"] for record in response.json()] == [
        first["decision_id"],
        second["decision_id"],
    ]
    assert [record["rationale"] for record in response.json()] == [
        "First",
        "Second",
    ]


def test_decision_record_reconstruction_diagnostics_and_summary(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    recommendations = PlannerRecommendationService(
        tmp_path / "recommendations.db",
        events=events,
    )
    decisions = DecisionRecordService(
        tmp_path / "decisions.db",
        events=events,
        recommendations=recommendations,
        runtime_sessions=sessions,
    )
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    session = sessions.create_session("reconstructed-decision-task")
    recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Reconstruct this selection",
            available_tools=[decision_tool()],
        ),
        PlannerResponse(
            proposed_tool=decision_tool(),
            rationale="Deterministic recommendation",
            confidence=0.8,
        ),
        {"governance_status": "ok"},
    )
    created = decisions.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Persist the selected recommendation",
    )
    reconstruction = ReconstructionService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
    )
    diagnostics = DiagnosticsService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
        decisions=decisions,
        reconstruction=reconstruction,
    )

    reconstructed = reconstruction.reconstruct_decision_records(session.id)

    assert reconstructed["decision_counts_by_type"] == {
        "recommendation_selection": 1
    }
    assert reconstructed["decisions"] == [
        {
            "decision_id": created.decision_id,
            "session_id": session.id,
            "task_id": session.task_id,
            "decision_type": "recommendation_selection",
            "selected_entity_id": recommendation.id,
            "selected_entity_type": "planner_recommendation",
            "rationale": "Persist the selected recommendation",
            "created_at": created.created_at.isoformat(),
        }
    ]
    assert diagnostics.decision_record_health() == {
        "decision_record_count": 1,
        "decision_record_counts_by_type": {
            "recommendation_selection": 1,
        },
    }
    assert diagnostics.runtime_summary()["decision_record_count"] == 1


def test_decision_record_rejects_missing_or_cross_session_entity() -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("decision-validation-task")
    other_session = runtime_session_service.create_session(
        "decision-validation-other-task"
    )
    other_recommendation = create_recommendation(
        other_session.id,
        other_session.task_id,
    )

    missing = client.post(
        f"/runtime/sessions/{session.id}/decision-records",
        json={
            "decision_type": "recommendation_selection",
            "selected_entity_id": "missing",
            "rationale": "Invalid",
        },
    )
    mismatched = client.post(
        f"/runtime/sessions/{session.id}/decision-records",
        json={
            "decision_type": "recommendation_selection",
            "selected_entity_id": other_recommendation.id,
            "rationale": "Wrong session",
        },
    )

    assert missing.status_code == 404
    assert mismatched.status_code == 409
    assert decision_record_service.list_decision_records(session.id) == []
