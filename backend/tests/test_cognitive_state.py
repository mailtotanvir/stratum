import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.runtime_event import EventType, Severity
from app.models.tool import Tool
from app.routes import runtime as runtime_routes
from app.services.cognitive_state_service import CognitiveStateService
from app.services.decision_evidence_service import DecisionEvidenceService
from app.services.decision_record_service import DecisionRecordService
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.planning_context_service import PlanningContextService
from app.services.proposal_service import ProposalService, proposal_service
from app.services.reconstruction_service import ReconstructionService
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.task_service import TaskService
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)
from app.services.trace_service import TraceService


def to_tool(record) -> Tool:
    return Tool(
        id=record.id,
        name=record.name,
        description=record.description,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        parameters=[],
    )


def create_recommendation(
    recommendations,
    session_id: str,
    task_id: str,
    tool: Tool,
    objective: str,
):
    return recommendations.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective=objective,
            available_tools=[tool],
        ),
        PlannerResponse(
            proposed_tool=tool,
            rationale=f"Recommendation for {objective}",
            confidence=0.8,
        ),
        {"governance_status": "ok"},
    )


def make_services(tmp_path):
    trace_path = tmp_path / "trace.db"
    events = EventService(TraceService(trace_path))
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
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
    evidence = DecisionEvidenceService(
        tmp_path / "evidence.db",
        events=events,
        decisions=decisions,
    )
    tools = ToolRegistryService(tmp_path / "tools.db", events=events)
    reconstruction = ReconstructionService(
        events=EventService(TraceService(trace_path)),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
    )
    diagnostics = DiagnosticsService(
        events=EventService(TraceService(trace_path)),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
        decisions=decisions,
        decision_evidence=evidence,
        reconstruction=reconstruction,
    )
    planning_context = PlanningContextService(
        sessions=sessions,
        proposals=proposals,
        recommendations=recommendations,
        tools=tools,
        diagnostics=diagnostics,
        events=EventService(TraceService(trace_path)),
    )
    cognitive = CognitiveStateService(
        planning_context=planning_context,
        recommendations=recommendations,
        proposals=proposals,
        decisions=decisions,
        evidence=evidence,
        diagnostics=diagnostics,
        sessions=sessions,
    )
    return {
        "trace_path": trace_path,
        "events": events,
        "sessions": sessions,
        "tasks": tasks,
        "proposals": proposals,
        "recommendations": recommendations,
        "decisions": decisions,
        "evidence": evidence,
        "tools": tools,
        "cognitive": cognitive,
    }


def test_cognitive_state_builds_counts_and_latest_ids(tmp_path) -> None:
    services = make_services(tmp_path)
    session = services["sessions"].create_session("cognitive-task")
    tool_record = services["tools"].register_tool(
        "shell.read",
        "Read workspace files",
    )
    services["tools"].register_tool(
        "shell.write",
        "Write workspace files",
        enabled=False,
    )
    tool = to_tool(tool_record)
    active = create_recommendation(
        services["recommendations"],
        session.id,
        session.task_id,
        tool,
        "Active",
    )
    promoted = create_recommendation(
        services["recommendations"],
        session.id,
        session.task_id,
        tool,
        "Promoted",
    )
    services["recommendations"].mark_promoted(promoted.id)
    dismissed = create_recommendation(
        services["recommendations"],
        session.id,
        session.task_id,
        tool,
        "Dismissed",
    )
    asyncio.run(services["recommendations"].dismiss(dismissed.id))

    resolved = services["proposals"].create_proposal(
        "Resolved",
        "Resolved proposal",
        task_id=session.task_id,
    )
    services["proposals"].respond(resolved.id, "approve")
    active_proposal = services["proposals"].create_proposal(
        "Active",
        "Active proposal",
        task_id=session.task_id,
    )
    first_decision = services["decisions"].create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=active.id,
        rationale="First decision",
    )
    latest_decision = services["decisions"].create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=promoted.id,
        rationale="Latest decision",
    )
    services["evidence"].create_evidence(
        decision_id=first_decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=active.id,
        summary="First evidence",
    )
    services["evidence"].create_evidence(
        decision_id=latest_decision.decision_id,
        evidence_type="governance_preview",
        evidence_reference="governance-preview:ok",
        summary="Latest evidence",
    )

    state = services["cognitive"].build(session.id)

    assert state.model_dump(mode="json") == {
        "session_id": session.id,
        "task_id": session.task_id,
        "active_recommendation_count": 1,
        "promoted_recommendation_count": 1,
        "dismissed_recommendation_count": 1,
        "active_proposal_count": 1,
        "decision_record_count": 2,
        "decision_evidence_count": 2,
        "latest_recommendation_id": dismissed.id,
        "latest_decision_id": latest_decision.decision_id,
        "latest_proposal_id": active_proposal.id,
        "available_tool_count": 1,
        "cognitive_health": "healthy",
    }


def test_cognitive_health_degrades_with_existing_diagnostics(tmp_path) -> None:
    services = make_services(tmp_path)
    session = services["sessions"].create_session("degraded-cognitive-task")
    services["events"].emit_event_sync(
        EventType.WARNING,
        "Existing warning",
        severity=Severity.WARNING,
    )

    state = services["cognitive"].build(session.id)

    assert state.cognitive_health.value == "degraded"


def test_cognitive_state_reconstructs_from_persisted_state(tmp_path) -> None:
    services = make_services(tmp_path)
    session = services["sessions"].create_session("reconstructed-cognitive-task")
    tool_record = services["tools"].register_tool(
        "shell.read",
        "Read workspace files",
    )
    recommendation = create_recommendation(
        services["recommendations"],
        session.id,
        session.task_id,
        to_tool(tool_record),
        "Persisted",
    )
    decision = services["decisions"].create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Persisted decision",
    )
    services["evidence"].create_evidence(
        decision_id=decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=recommendation.id,
        summary="Persisted evidence",
    )

    rebuilt = make_services(tmp_path)["cognitive"]

    assert rebuilt.reconstruct(session.id) == services["cognitive"].build(
        session.id
    )


def test_cognitive_state_endpoint_is_read_only(monkeypatch) -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("cognitive-endpoint-task")
    tool_record = tool_registry_service.register_tool(
        "shell.read",
        "Read workspace files",
    )
    recommendation = create_recommendation(
        planner_recommendation_service,
        session.id,
        session.task_id,
        to_tool(tool_record),
        "Endpoint",
    )

    def fail(*args, **kwargs):
        raise AssertionError("cognitive state must remain read only")

    async def fail_async(*args, **kwargs):
        raise AssertionError("cognitive state must not invoke runtime behavior")

    monkeypatch.setattr(proposal_service, "create_proposal", fail)
    monkeypatch.setattr(proposal_service, "create_proposal_async", fail_async)
    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail_async)
    monkeypatch.setattr(runtime_routes.work_loop_service, "run_single_step", fail_async)
    monkeypatch.setattr(tool_invocation_service, "create_invocation", fail)
    monkeypatch.setattr(tool_execution_service, "execute_invocation", fail_async)

    proposals_before = proposal_service.list_proposals(task_id=session.task_id)
    invocations_before = tool_invocation_service.list_invocations(
        session_id=session.id
    )
    events_before = event_service.list_persisted_events()

    response = client.get(
        f"/runtime/sessions/{session.id}/cognitive-state"
    )
    reconstructed = client.get(
        f"/reconstruct/cognitive-state/{session.id}"
    )

    assert response.status_code == 200
    assert reconstructed.status_code == 200
    assert reconstructed.json() == response.json()
    assert response.json()["latest_recommendation_id"] == recommendation.id
    assert proposal_service.list_proposals(
        task_id=session.task_id
    ) == proposals_before
    assert tool_invocation_service.list_invocations(
        session_id=session.id
    ) == invocations_before
    assert event_service.list_persisted_events() == events_before


def test_cognitive_state_diagnostics_are_derived(tmp_path) -> None:
    services = make_services(tmp_path)
    services["sessions"].create_session("healthy-session")
    services["sessions"].create_session("second-healthy-session")

    assert services["cognitive"].diagnostics() == {
        "cognitive_state_generated_count": 2,
        "cognitive_health_distribution": {
            "healthy": 2,
            "degraded": 0,
        },
    }
