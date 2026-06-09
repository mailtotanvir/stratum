from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    decision_evidence_service,
)
from app.services.decision_projection_builder_service import (
    DECISION_PROJECTION_SOURCE,
    DecisionProjectionBuilderService,
    decision_projection_builder_service,
)
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.decision_trail_service import DecisionTrailService
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
from app.services.trace_service import TraceService


def projection_tool() -> Tool:
    return Tool(
        id="projection-tool",
        name="shell.read",
        description="Read workspace files",
        enabled=True,
        created_at="2026-06-09T00:00:00+00:00",
        updated_at="2026-06-09T00:00:00+00:00",
        parameters=[],
    )


def make_projection_fixture(tmp_path):
    trace_path = tmp_path / "trace.db"
    events = EventService(TraceService(trace_path))
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
    evidence = DecisionEvidenceService(
        tmp_path / "evidence.db",
        events=events,
        decisions=decisions,
    )
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    trails = DecisionTrailService(
        ReconstructionService(
            events=EventService(TraceService(trace_path)),
            proposals=proposals,
            recommendations=recommendations,
        )
    )
    builder = DecisionProjectionBuilderService(
        sessions=sessions,
        decisions=decisions,
        evidence=evidence,
        trails=trails,
        recommendations=recommendations,
        events=events,
    )

    session = sessions.create_session("decision-projection-task")
    recommendation = recommendations.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Build a deterministic projection",
            available_tools=[projection_tool()],
        ),
        PlannerResponse(
            proposed_tool=projection_tool(),
            rationale="Canonical recommendation",
            confidence=0.9,
        ),
        {"governance_status": "ok"},
    )
    decision = decisions.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Selected canonical recommendation",
    )
    evidence.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=recommendation.id,
        summary="Recommendation evidence",
    )
    evidence.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="governance_preview",
        evidence_reference="governance-preview:ok",
        summary="Governance evidence",
    )
    proposals.create_proposal(
        title="Decision-backed proposal",
        body="Projection trail source",
        task_id=session.task_id,
        source_type="planner_recommendation",
        source_id=recommendation.id,
    )
    recommendations.mark_promoted(recommendation.id)

    return {
        "builder": builder,
        "decisions": decisions,
        "evidence": evidence,
        "events": events,
        "recommendations": recommendations,
        "sessions": sessions,
        "session": session,
        "decision": decision,
        "recommendation": recommendation,
    }


def session_state(record) -> tuple:
    return (
        record.id,
        record.task_id,
        record.status,
        record.created_at,
        record.completed_at,
    )


def recommendation_state(record) -> tuple:
    return (
        record.id,
        record.session_id,
        record.task_id,
        record.status,
        record.created_at,
    )


def decision_state(record) -> tuple:
    return (
        record.decision_id,
        record.session_id,
        record.task_id,
        record.decision_type,
        record.selected_entity_id,
        record.selected_entity_type,
        record.rationale,
        record.created_at,
    )


def evidence_state(record) -> tuple:
    return (
        record.evidence_id,
        record.decision_id,
        record.evidence_type,
        record.evidence_reference,
        record.summary,
        record.created_at,
    )


def test_decision_projection_build_is_deterministic_and_recreates_instances(
    tmp_path,
) -> None:
    fixture = make_projection_fixture(tmp_path)

    first = fixture["builder"].build(fixture["session"].id)
    second = fixture["builder"].build(fixture["session"].id)

    assert first == second
    assert first is not second
    assert first[0] is not second[0]
    assert first[0].model_dump(mode="json") == {
        "decision_id": fixture["decision"].decision_id,
        "recommendation_id": fixture["recommendation"].id,
        "status": "promoted",
        "selected_at": fixture["decision"].created_at.isoformat(),
        "evidence_count": 2,
        "trail_entry_count": 1,
    }


def test_decision_projection_is_not_authoritative_and_preserves_session_state(
    tmp_path,
) -> None:
    fixture = make_projection_fixture(tmp_path)
    session_before = session_state(
        fixture["sessions"].get_session(fixture["session"].id)
    )
    recommendation_before = recommendation_state(
        fixture["recommendations"].get_recommendation(
            fixture["recommendation"].id
        )
    )
    decisions_before = [
        decision_state(record)
        for record in fixture["decisions"].list_decision_records(
            fixture["session"].id
        )
    ]
    evidence_before = [
        evidence_state(record)
        for record in fixture["evidence"].list_evidence(
            fixture["decision"].decision_id
        )
    ]

    projection = fixture["builder"].build(fixture["session"].id)[0]
    projection.evidence_count = 999
    projection.status = "dismissed"
    rebuilt = fixture["builder"].build(fixture["session"].id)[0]

    assert rebuilt.evidence_count == 2
    assert rebuilt.status.value == "promoted"
    assert session_state(
        fixture["sessions"].get_session(fixture["session"].id)
    ) == session_before
    assert recommendation_state(
        fixture["recommendations"].get_recommendation(
            fixture["recommendation"].id
        )
    ) == recommendation_before
    assert [
        decision_state(record)
        for record in fixture["decisions"].list_decision_records(
            fixture["session"].id
        )
    ] == decisions_before
    assert [
        evidence_state(record)
        for record in fixture["evidence"].list_evidence(
            fixture["decision"].decision_id
        )
    ] == evidence_before


def test_decision_projection_emits_compact_diagnostic_event(tmp_path) -> None:
    fixture = make_projection_fixture(tmp_path)

    fixture["builder"].build(fixture["session"].id)

    events = fixture["events"].list_persisted_events(
        event_type="decision_projection_built"
    )
    assert len(events) == 1
    assert events[0].metadata == {
        "session_id": fixture["session"].id,
        "projection_count": 1,
        "source": DECISION_PROJECTION_SOURCE,
    }


def create_endpoint_projection():
    session = runtime_session_service.create_session(
        "decision-projection-endpoint-task"
    )
    recommendation = planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Inspect decision projections",
            available_tools=[projection_tool()],
        ),
        PlannerResponse(
            proposed_tool=projection_tool(),
            rationale="Endpoint recommendation",
            confidence=0.85,
        ),
        {"governance_status": "ok"},
    )
    decision = decision_record_service.create_decision_record(
        session_id=session.id,
        decision_type="recommendation_selection",
        selected_entity_id=recommendation.id,
        rationale="Endpoint selection",
    )
    evidence = decision_evidence_service.create_evidence(
        decision_id=decision.decision_id,
        evidence_type="recommendation",
        evidence_reference=recommendation.id,
        summary="Sensitive evidence summary",
    )
    proposal = proposal_service.create_proposal(
        title="Endpoint projection proposal",
        body="Sensitive trail body",
        task_id=session.task_id,
        source_type="planner_recommendation",
        source_id=recommendation.id,
    )
    planner_recommendation_service.mark_promoted(recommendation.id)
    return session, recommendation, decision, evidence, proposal


def test_decision_projection_endpoint_rebuilds_read_only_summaries() -> None:
    client = TestClient(app)
    session, recommendation, decision, evidence, proposal = (
        create_endpoint_projection()
    )
    session_before = session_state(
        runtime_session_service.get_session(session.id)
    )

    first = client.get(
        f"/runtime/sessions/{session.id}/decision-projections"
    )
    second = client.get(
        f"/runtime/sessions/{session.id}/decision-projections"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json() == {
        "session_id": session.id,
        "projection_count": 1,
        "selected_decision_count": 1,
        "pending_decision_count": 0,
        "rejected_decision_count": 0,
        "projections": [
            {
                "decision_id": decision.decision_id,
                "recommendation_id": recommendation.id,
                "status": "promoted",
                "selected_at": decision.created_at.isoformat(),
                "evidence_count": 1,
                "trail_entry_count": 1,
            }
        ],
    }
    response_text = first.text
    assert evidence.evidence_id not in response_text
    assert evidence.summary not in response_text
    assert proposal.id not in response_text
    assert proposal.body not in response_text
    assert "evidence_ids" not in response_text
    assert "proposal_id" not in response_text
    assert "planning_context" not in response_text
    assert "cognitive_state" not in response_text
    assert session_state(
        runtime_session_service.get_session(session.id)
    ) == session_before

    build_events = event_service.list_persisted_events(
        event_type="decision_projection_built"
    )
    assert len(build_events) == 2
    assert all(
        event.metadata["session_id"] == session.id
        for event in build_events
    )
    session_build_events = event_service.list_persisted_events(
        event_type="session_decision_projection_built"
    )
    assert len(session_build_events) == 2
    assert all(
        event.metadata == {
            "session_id": session.id,
            "projection_count": 1,
            "source": "session_decision_projection_builder",
        }
        for event in session_build_events
    )


def test_builder_and_endpoint_reconstruct_equivalent_projection_summaries() -> None:
    client = TestClient(app)
    session, _, _, evidence, proposal = create_endpoint_projection()

    direct_before = [
        projection.model_dump(mode="json")
        for projection in decision_projection_builder_service.build(session.id)
    ]
    first_response = client.get(
        f"/runtime/sessions/{session.id}/decision-projections"
    )
    second_response = client.get(
        f"/runtime/sessions/{session.id}/decision-projections"
    )
    direct_after = [
        projection.model_dump(mode="json")
        for projection in decision_projection_builder_service.build(session.id)
    ]

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first = first_response.json()
    second = second_response.json()
    assert direct_before == first["projections"]
    assert first["projections"] == second["projections"]
    assert second["projections"] == direct_after
    assert first["projection_count"] == len(direct_before)
    assert second["projection_count"] == len(direct_after)
    assert first["selected_decision_count"] == 1
    assert first["pending_decision_count"] == 0
    assert first["rejected_decision_count"] == 0
    assert second["selected_decision_count"] == 1
    assert second["pending_decision_count"] == 0
    assert second["rejected_decision_count"] == 0
    assert set(first["projections"][0]) == {
        "decision_id",
        "recommendation_id",
        "status",
        "selected_at",
        "evidence_count",
        "trail_entry_count",
    }

    build_events = event_service.list_persisted_events(
        event_type="decision_projection_built"
    )
    assert len(build_events) == 4
    session_build_events = event_service.list_persisted_events(
        event_type="session_decision_projection_built"
    )
    assert len(session_build_events) == 2
    assert direct_before == direct_after

    response_text = first_response.text
    assert evidence.evidence_id not in response_text
    assert evidence.summary not in response_text
    assert proposal.id not in response_text
    assert proposal.body not in response_text
    for excluded_key in (
        "evidence_ids",
        "evidence_reference",
        "summary",
        "proposal_id",
        "source_type",
        "planning_context",
        "cognitive_state",
        "planner_response",
    ):
        assert excluded_key not in response_text


def test_decision_projection_endpoint_returns_standard_missing_session() -> None:
    response = TestClient(app).get(
        "/runtime/sessions/missing-session/decision-projections"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Runtime session not found: missing-session"
    }
