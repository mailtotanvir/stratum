from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.routes import runtime as runtime_routes
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    decision_evidence_service,
)
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.decision_trail_service import DecisionTrailService
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService
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
from app.services.task_service import TaskService
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.trace_service import TraceService


def trail_tool() -> Tool:
    return Tool(
        id="trail-tool",
        name="shell.read",
        description="Read only",
        enabled=True,
        created_at="2026-06-07T00:00:00+00:00",
        updated_at="2026-06-07T00:00:00+00:00",
        parameters=[],
    )


def create_global_recommendation(session_id: str, task_id: str):
    return planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective="Build decision trail",
            available_tools=[trail_tool()],
        ),
        PlannerResponse(
            proposed_tool=trail_tool(),
            rationale="Deterministic recommendation",
            confidence=0.9,
        ),
        {"governance_status": "ok"},
    )


def create_complete_global_trail():
    session = runtime_session_service.create_session("decision-trail-task")
    recommendation = create_global_recommendation(
        session.id,
        session.task_id,
    )
    decision = decision_record_service.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Selected recommendation",
    )
    evidence = decision_evidence_service.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=recommendation.id,
        summary="Recommendation evidence",
    )
    proposal = proposal_service.create_proposal(
        title="Decision-backed proposal",
        body="Derived proposal lineage",
        task_id=session.task_id,
        source_type="planner_recommendation",
        source_id=recommendation.id,
    )
    return session, recommendation, decision, evidence, proposal


def test_complete_decision_trail_endpoint_is_read_only(monkeypatch) -> None:
    client = TestClient(app)
    session, recommendation, decision, evidence, proposal = (
        create_complete_global_trail()
    )

    async def fail(*args, **kwargs):
        raise AssertionError("decision trail retrieval must remain read-only")

    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail)
    monkeypatch.setattr(runtime_routes.work_loop_service, "run_single_step", fail)
    monkeypatch.setattr(tool_execution_service, "execute_invocation", fail)
    monkeypatch.setattr(runtime_routes.python_async_runtime, "run_task", fail)

    proposal_ids_before = [
        record.id
        for record in proposal_service.list_proposals(task_id=session.task_id)
    ]
    invocations_before = tool_invocation_service.list_invocations(
        session_id=session.id
    )
    executions_before = runtime_routes.runtime_execution_service.list()

    response = client.get(f"/proposals/{proposal.id}/decision-trail")

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": proposal.id,
        "recommendation_id": recommendation.id,
        "decision_id": decision.decision_id,
        "evidence_ids": [evidence.evidence_id],
        "source_type": "planner_recommendation",
        "created_at": proposal.created_at.isoformat(),
    }
    assert [
        record.id
        for record in proposal_service.list_proposals(task_id=session.task_id)
    ] == proposal_ids_before
    assert tool_invocation_service.list_invocations(
        session_id=session.id
    ) == invocations_before
    assert runtime_routes.runtime_execution_service.list() == executions_before


def test_partial_decision_trail_endpoint_does_not_fail() -> None:
    client = TestClient(app)
    proposal = proposal_service.create_proposal(
        title="Manual proposal",
        body="No recommendation lineage",
    )

    response = client.get(f"/proposals/{proposal.id}/decision-trail")

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": proposal.id,
        "recommendation_id": None,
        "decision_id": None,
        "evidence_ids": [],
        "source_type": "manual",
        "created_at": proposal.created_at.isoformat(),
    }


def test_decision_trail_reconstructs_entirely_from_events(tmp_path) -> None:
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
    evidence_service = DecisionEvidenceService(
        tmp_path / "evidence.db",
        events=events,
        decisions=decisions,
    )
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    session = sessions.create_session("reconstructed-trail-task")
    recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Reconstruct trail",
            available_tools=[trail_tool()],
        ),
        PlannerResponse(
            proposed_tool=trail_tool(),
            rationale="Deterministic recommendation",
            confidence=0.8,
        ),
        {"governance_status": "ok"},
    )
    decision = decisions.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Selected for reconstruction",
    )
    evidence = evidence_service.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="governance_preview",
        evidence_reference="governance-preview:ok",
        summary="Governance evidence",
    )
    proposal = proposals.create_proposal(
        title="Reconstructed proposal",
        body="Event-derived trail",
        source_type="planner_recommendation",
        source_id=recommendation.id,
    )
    reconstruction = ReconstructionService(events=EventService(trace_store))
    service = DecisionTrailService(reconstruction)

    trail = service.reconstruct(proposal.id)

    assert trail.proposal_id == proposal.id
    assert trail.recommendation_id == recommendation.id
    assert trail.decision_id == decision.decision_id
    assert trail.evidence_ids == [evidence.evidence_id]
    assert service.reconstruct_all() == [trail]


def test_decision_trail_diagnostics_surface_each_lineage_gap(tmp_path) -> None:
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
    evidence_service = DecisionEvidenceService(
        tmp_path / "evidence.db",
        events=events,
        decisions=decisions,
    )
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    tasks = TaskService(tmp_path / "tasks.db", events=events)

    missing_recommendation = proposals.create_proposal(
        title="Missing recommendation",
        body="Broken source",
        source_type="planner_recommendation",
        source_id="missing-recommendation",
    )

    session = sessions.create_session("trail-gap-task")
    recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Gap diagnostics",
            available_tools=[trail_tool()],
        ),
        PlannerResponse(
            proposed_tool=trail_tool(),
            rationale="Deterministic recommendation",
            confidence=0.7,
        ),
        {"governance_status": "ok"},
    )
    missing_decision = proposals.create_proposal(
        title="Missing decision",
        body="Recommendation only",
        source_type="planner_recommendation",
        source_id=recommendation.id,
    )

    decision = decisions.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Decision without evidence",
    )
    missing_evidence = proposals.create_proposal(
        title="Missing evidence",
        body="Decision without evidence",
        source_type="planner_recommendation",
        source_id=recommendation.id,
    )

    complete_session = sessions.create_session("complete-trail-task")
    complete_recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=complete_session.task_id,
            session_id=complete_session.id,
            objective="Complete diagnostics",
            available_tools=[trail_tool()],
        ),
        PlannerResponse(
            proposed_tool=trail_tool(),
            rationale="Complete recommendation",
            confidence=0.9,
        ),
        {"governance_status": "ok"},
    )
    complete_decision = decisions.create_decision_record(
        session_id=complete_session.id,
        decision_type="recommendation_selection",
        selected_entity_id=complete_recommendation.id,
        rationale="Complete decision",
    )
    evidence_service.create_evidence(
        decision_id=complete_decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=complete_recommendation.id,
        summary="Complete evidence",
    )
    complete_proposal = proposals.create_proposal(
        title="Complete trail",
        body="Complete lineage",
        source_type="planner_recommendation",
        source_id=complete_recommendation.id,
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
        decision_evidence=evidence_service,
        reconstruction=reconstruction,
    )

    health = diagnostics.decision_trail_health()
    issues = {
        issue["proposal_id"]: issue["issue_type"]
        for issue in health["decision_trail_issues"]
    }

    assert issues[missing_recommendation.id] == (
        "proposal_missing_recommendation_source"
    )
    assert issues[missing_decision.id] == (
        "recommendation_missing_decision_record"
    )
    assert issues[missing_evidence.id] == "decision_record_missing_evidence"
    assert complete_proposal.id not in issues
    assert health["proposals_with_decision_trails"] == 1
    assert health["proposals_missing_decision_trails"] == 3
    assert health["decision_trail_completeness"] == 0.25
    assert diagnostics.runtime_summary()["decision_trail_count"] == 1
