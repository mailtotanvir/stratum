from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.routes import runtime as runtime_routes
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.planning_context_service import PlanningContextService
from app.services.proposal_service import ProposalService, proposal_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)
from app.services.trace_service import TraceService


def to_tool(record, service=tool_registry_service) -> Tool:
    return Tool(
        id=record.id,
        name=record.name,
        description=record.description,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        parameters=[],
    )


def create_recommendation(session_id: str, task_id: str, tool: Tool):
    return planner_recommendation_service.create_recommendation(
        planner_request=PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective="Inspect persisted runtime state",
            available_tools=[tool],
            context={},
        ),
        planner_response=PlannerResponse(
            proposed_tool=tool,
            rationale="Use the available read tool.",
            confidence=0.75,
        ),
        governance_preview={"governance_status": "healthy"},
    )


def test_planning_context_endpoint_builds_from_runtime_state() -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("task-planning-context")
    enabled_tool = tool_registry_service.register_tool(
        name="shell.read",
        description="Read workspace files",
    )
    disabled_tool = tool_registry_service.register_tool(
        name="shell.write",
        description="Write workspace files",
        enabled=False,
    )
    active_proposal = proposal_service.create_proposal(
        title="Inspect current state",
        body="Read-only proposal",
        task_id=session.task_id,
    )
    resolved_proposal = proposal_service.create_proposal(
        title="Already handled",
        body="Resolved proposal",
        task_id=session.task_id,
    )
    proposal_service.respond(resolved_proposal.id, "approve")
    recommendation = create_recommendation(
        session.id,
        session.task_id,
        to_tool(enabled_tool),
    )

    response = client.get(
        f"/runtime/sessions/{session.id}/planning-context"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.id
    assert body["task_id"] == session.task_id
    assert [item["id"] for item in body["active_proposals"]] == [
        active_proposal.id
    ]
    assert [item["id"] for item in body["active_recommendations"]] == [
        recommendation.id
    ]
    assert [item["id"] for item in body["available_tools"]] == [
        enabled_tool.id
    ]
    assert disabled_tool.id not in {
        item["id"] for item in body["available_tools"]
    }
    assert body["recent_events"]
    assert body["diagnostics_summary"]["proposal_count"] == 1
    assert body["diagnostics_summary"]["recommendation_count"] == 1
    assert body["diagnostics_summary"]["available_tool_count"] == 1
    assert body["diagnostics_summary"]["governance_status"] == "ok"


def test_planning_context_reconstructs_from_persisted_state(tmp_path) -> None:
    session_db = tmp_path / "sessions.db"
    proposal_db = tmp_path / "proposals.db"
    recommendation_db = tmp_path / "recommendations.db"
    tool_db = tmp_path / "tools.db"
    trace_db = tmp_path / "trace.db"
    events = EventService(TraceService(trace_db))
    sessions = RuntimeSessionService(session_db)
    proposals = ProposalService(proposal_db, events=events)
    recommendations = PlannerRecommendationService(
        recommendation_db,
        events=events,
    )
    tools = ToolRegistryService(tool_db, events=events)

    session = sessions.create_session("task-reconstructed-context")
    tool_record = tools.register_tool("shell.read", "Read workspace files")
    proposal = proposals.create_proposal(
        "Inspect persisted state",
        "Read only",
        task_id=session.task_id,
    )
    recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Reconstruct context",
            available_tools=[to_tool(tool_record, tools)],
            context={},
        ),
        PlannerResponse(
            proposed_tool=to_tool(tool_record, tools),
            rationale="Use persisted tool metadata.",
            confidence=0.5,
        ),
        {"governance_status": "healthy"},
    )

    reconstructed_events = EventService(TraceService(trace_db))
    reconstructed_service = PlanningContextService(
        sessions=RuntimeSessionService(session_db),
        proposals=ProposalService(proposal_db, events=reconstructed_events),
        recommendations=PlannerRecommendationService(
            recommendation_db,
            events=reconstructed_events,
        ),
        tools=ToolRegistryService(tool_db, events=reconstructed_events),
        diagnostics=DiagnosticsService(events=reconstructed_events),
        events=reconstructed_events,
    )

    first = reconstructed_service.build(session.id)
    second = reconstructed_service.build(session.id)

    assert first == second
    assert first.active_proposals[0].id == proposal.id
    assert first.active_recommendations[0].id == recommendation.id
    assert first.available_tools[0].id == tool_record.id
    assert first.recent_events[-1].type == "planner_recommendation_created"


def test_planning_context_read_has_no_runtime_side_effects(monkeypatch) -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("task-read-only-context")
    tool_registry_service.register_tool("shell.read", "Read workspace files")
    proposal_service.create_proposal(
        "Existing proposal",
        "Must remain unchanged",
        task_id=session.task_id,
    )
    events_before = event_service.list_persisted_events()

    def fail(*args, **kwargs):
        raise AssertionError("planning context must be read only")

    async def fail_async(*args, **kwargs):
        raise AssertionError("planning context must not call a provider or execute")

    monkeypatch.setattr(proposal_service, "create_proposal", fail)
    monkeypatch.setattr(proposal_service, "create_proposal_async", fail_async)
    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail_async)
    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_async,
    )
    monkeypatch.setattr(tool_invocation_service, "create_invocation", fail)
    monkeypatch.setattr(
        tool_invocation_service,
        "create_invocation_without_event",
        fail,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_async,
    )

    response = client.get(
        f"/runtime/sessions/{session.id}/planning-context"
    )

    assert response.status_code == 200
    assert len(proposal_service.list_proposals(task_id=session.task_id)) == 1
    assert tool_invocation_service.list_invocations(session_id=session.id) == []
    assert event_service.list_persisted_events() == events_before


def test_planning_context_unknown_session_returns_404() -> None:
    response = TestClient(app).get(
        "/runtime/sessions/missing-session/planning-context"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Runtime session not found: missing-session"
    )
