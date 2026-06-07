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
from app.services.task_service import TaskService
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.trace_service import TraceService


def evidence_tool() -> Tool:
    return Tool(
        id="evidence-tool",
        name="shell.read",
        description="Read only",
        enabled=True,
        created_at="2026-06-07T00:00:00+00:00",
        updated_at="2026-06-07T00:00:00+00:00",
        parameters=[],
    )


def create_decision():
    session = runtime_session_service.create_session("evidence-task")
    recommendation = planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Support this decision",
            available_tools=[evidence_tool()],
        ),
        PlannerResponse(
            proposed_tool=evidence_tool(),
            rationale="Deterministic recommendation",
            confidence=0.9,
        ),
        {"governance_status": "ok"},
    )
    decision = decision_record_service.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Selected recommendation",
    )
    return session, recommendation, decision


def test_evidence_creation_is_linked_and_audit_only(monkeypatch) -> None:
    client = TestClient(app)
    session, recommendation, decision = create_decision()

    async def fail(*args, **kwargs):
        raise AssertionError("evidence creation must not invoke runtime behavior")

    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail)
    monkeypatch.setattr(runtime_routes.work_loop_service, "run_single_step", fail)
    monkeypatch.setattr(tool_execution_service, "execute_invocation", fail)
    monkeypatch.setattr(runtime_routes.python_async_runtime, "run_task", fail)

    proposals_before = proposal_service.list_proposals(task_id=session.task_id)
    invocations_before = tool_invocation_service.list_invocations(
        session_id=session.id
    )
    executions_before = runtime_routes.runtime_execution_service.list()

    response = client.post(
        f"/decision-records/{decision.decision_id}/evidence",
        json={
            "evidence_type": "recommendation",
            "evidence_reference": recommendation.id,
            "summary": "Selected recommendation record",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision_id"] == decision.decision_id
    assert body["evidence_type"] == "recommendation"
    assert body["evidence_reference"] == recommendation.id
    assert body["summary"] == "Selected recommendation record"
    assert decision_evidence_service.get_evidence(
        body["evidence_id"]
    ).decision_id == decision.decision_id

    events = event_service.list_persisted_events(
        event_type="decision_evidence_created"
    )
    assert len(events) == 1
    assert events[0].metadata["decision_id"] == decision.decision_id
    assert events[0].metadata["evidence_id"] == body["evidence_id"]
    assert events[0].metadata["evidence_type"] == "recommendation"

    assert proposal_service.list_proposals(
        task_id=session.task_id
    ) == proposals_before
    assert tool_invocation_service.list_invocations(
        session_id=session.id
    ) == invocations_before
    assert runtime_routes.runtime_execution_service.list() == executions_before


def test_evidence_listing_is_ordered_and_supports_initial_types() -> None:
    client = TestClient(app)
    _, recommendation, decision = create_decision()
    evidence = [
        ("recommendation", recommendation.id, "Recommendation"),
        (
            "planning_context_snapshot",
            "planning-context-snapshot:v1",
            "Planning context",
        ),
        ("governance_preview", "governance-preview:ok", "Governance preview"),
    ]

    created = [
        client.post(
            f"/decision-records/{decision.decision_id}/evidence",
            json={
                "evidence_type": evidence_type,
                "evidence_reference": reference,
                "summary": summary,
            },
        ).json()
        for evidence_type, reference, summary in evidence
    ]

    response = client.get(
        f"/decision-records/{decision.decision_id}/evidence"
    )

    assert response.status_code == 200
    assert [item["evidence_id"] for item in response.json()] == [
        item["evidence_id"] for item in created
    ]
    assert [item["evidence_type"] for item in response.json()] == [
        item[0] for item in evidence
    ]


def test_evidence_reconstruction_diagnostics_and_summary(tmp_path) -> None:
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
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    session = sessions.create_session("evidence-reconstruction-task")
    recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Reconstruct evidence",
            available_tools=[evidence_tool()],
        ),
        PlannerResponse(
            proposed_tool=evidence_tool(),
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
    first = evidence_service.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=recommendation.id,
        summary="Recommendation evidence",
    )
    second = evidence_service.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="governance_preview",
        evidence_reference="governance-preview:ok",
        summary="Governance evidence",
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

    reconstructed = reconstruction.reconstruct_decision_evidence(
        decision.decision_id
    )

    assert reconstructed["evidence_count"] == 2
    assert reconstructed["evidence_counts_by_type"] == {
        "recommendation": 1,
        "governance_preview": 1,
    }
    assert reconstructed["evidence_by_decision"][decision.decision_id] == [
        {
            "evidence_id": first.evidence_id,
            "decision_id": decision.decision_id,
            "evidence_type": "recommendation",
            "evidence_reference": recommendation.id,
            "summary": "Recommendation evidence",
            "created_at": first.created_at.isoformat(),
        },
        {
            "evidence_id": second.evidence_id,
            "decision_id": decision.decision_id,
            "evidence_type": "governance_preview",
            "evidence_reference": "governance-preview:ok",
            "summary": "Governance evidence",
            "created_at": second.created_at.isoformat(),
        },
    ]
    assert diagnostics.decision_evidence_health() == {
        "decision_evidence_count": 2,
        "decision_evidence_counts_by_type": {
            "recommendation": 1,
            "governance_preview": 1,
        },
    }
    assert diagnostics.runtime_summary()["decision_evidence_count"] == 2


def test_evidence_rejects_missing_decision() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/decision-records/missing/evidence",
        json={
            "evidence_type": "recommendation",
            "evidence_reference": "recommendation-1",
            "summary": "Missing parent",
        },
    )
    list_response = client.get("/decision-records/missing/evidence")

    assert create_response.status_code == 404
    assert list_response.status_code == 404
    assert decision_evidence_service.list_evidence() == []


def test_decision_creation_does_not_automatically_create_evidence() -> None:
    _, _, decision = create_decision()

    assert decision_evidence_service.list_evidence(decision.decision_id) == []
