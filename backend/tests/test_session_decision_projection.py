import asyncio
from datetime import UTC, datetime, timedelta

from app.models.planner import PlannerRequest, PlannerResponse
from app.models.projection import Projection
from app.models.tool import Tool
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.decision_evidence_service import DecisionEvidenceService
from app.services.decision_projection_builder_service import (
    DecisionProjectionBuilderService,
)
from app.services.decision_record_service import DecisionRecordService
from app.services.decision_trail_service import DecisionTrailService
from app.services.event_service import EventService
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
)
from app.services.proposal_service import ProposalService
from app.services.reconstruction_service import ReconstructionService
from app.services.runtime_session_service import RuntimeSessionService
from app.services.session_decision_projection_builder_service import (
    SESSION_DECISION_PROJECTION_SCHEMA_VERSION,
    SESSION_DECISION_PROJECTION_SOURCE,
    SESSION_DECISION_PROJECTION_TYPE,
    SessionDecisionProjectionBuilderService,
)
from app.services.trace_service import TraceService


def session_projection_tool() -> Tool:
    return Tool(
        id="session-projection-tool",
        name="shell.read",
        description="Read workspace files",
        enabled=True,
        created_at="2026-06-09T00:00:00+00:00",
        updated_at="2026-06-09T00:00:00+00:00",
        parameters=[],
    )


def create_recommendation(
    recommendations: PlannerRecommendationService,
    session_id: str,
    task_id: str,
    objective: str,
):
    return recommendations.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective=objective,
            available_tools=[session_projection_tool()],
        ),
        PlannerResponse(
            proposed_tool=session_projection_tool(),
            rationale=f"Recommendation for {objective}",
            confidence=0.8,
        ),
        {"governance_status": "ok"},
    )


def make_session_projection_fixture(
    tmp_path,
    decision_clock=None,
    session_clock=None,
):
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
    decision_projections = DecisionProjectionBuilderService(
        sessions=sessions,
        decisions=decisions,
        evidence=evidence,
        trails=DecisionTrailService(
            ReconstructionService(
                events=EventService(TraceService(trace_path)),
                proposals=proposals,
                recommendations=recommendations,
            )
        ),
        recommendations=recommendations,
        events=events,
        clock=decision_clock,
    )
    builder = SessionDecisionProjectionBuilderService(
        projections=decision_projections,
        events=events,
        clock=session_clock,
    )

    session = sessions.create_session("session-decision-projection-task")
    active = create_recommendation(
        recommendations,
        session.id,
        session.task_id,
        "Pending decision",
    )
    promoted = create_recommendation(
        recommendations,
        session.id,
        session.task_id,
        "Selected decision",
    )
    dismissed = create_recommendation(
        recommendations,
        session.id,
        session.task_id,
        "Rejected decision",
    )
    for recommendation in (active, promoted, dismissed):
        decisions.create_decision_record(
            session_id=session.id,
            decision_type="recommendation_selection",
            selected_entity_id=recommendation.id,
            rationale=f"Decision for {recommendation.objective}",
        )
    recommendations.mark_promoted(promoted.id)
    asyncio.run(recommendations.dismiss(dismissed.id))

    return {
        "builder": builder,
        "events": events,
        "session": session,
        "sessions": sessions,
    }


def session_state(record) -> tuple:
    return (
        record.id,
        record.task_id,
        record.status,
        record.created_at,
        record.completed_at,
    )


def projection_payload(projection):
    return projection.model_dump(
        mode="json",
        exclude={
            "metadata": True,
            "projections": {"__all__": {"metadata"}},
        },
    )


def test_session_projection_builder_satisfies_common_contract(tmp_path) -> None:
    fixture = make_session_projection_fixture(tmp_path)

    result = fixture["builder"].build(fixture["session"].id)

    assert isinstance(fixture["builder"], BaseProjectionBuilder)
    assert isinstance(result, Projection)


def test_session_decision_projection_rebuild_is_stable_and_fresh(
    tmp_path,
) -> None:
    first_built_at = datetime(2026, 6, 10, 13, 0, tzinfo=UTC)
    session_build_times = iter(
        [first_built_at, first_built_at + timedelta(minutes=1)]
    )
    fixture = make_session_projection_fixture(
        tmp_path,
        session_clock=lambda: next(session_build_times),
    )

    first = fixture["builder"].build(fixture["session"].id)
    second = fixture["builder"].build(fixture["session"].id)

    assert projection_payload(first) == projection_payload(second)
    assert first is not second
    assert first.metadata is not second.metadata
    assert first.metadata.built_at == first_built_at
    assert second.metadata.built_at == first_built_at + timedelta(minutes=1)
    assert first.metadata.projection_type == SESSION_DECISION_PROJECTION_TYPE
    assert (
        first.metadata.builder_name
        == "SessionDecisionProjectionBuilderService"
    )
    assert first.metadata.source == SESSION_DECISION_PROJECTION_SOURCE
    assert (
        first.metadata.schema_version
        == SESSION_DECISION_PROJECTION_SCHEMA_VERSION
    )
    assert first.metadata.reconstruction.model_dump() == {
        "projection_type": SESSION_DECISION_PROJECTION_TYPE,
        "reconstruction_source": "decision_projection",
        "rebuildable": True,
        "authoritative_source": "runtime_session",
    }
    assert first.projections is not second.projections
    assert all(
        first_projection is not second_projection
        for first_projection, second_projection in zip(
            first.projections,
            second.projections,
            strict=True,
        )
    )
    assert first.projection_count == 3
    assert first.selected_decision_count == 1
    assert first.pending_decision_count == 1
    assert first.rejected_decision_count == 1
    assert {
        projection.status.value for projection in first.projections
    } == {"active", "promoted", "dismissed"}


def test_session_decision_projection_does_not_mutate_session_state(
    tmp_path,
) -> None:
    fixture = make_session_projection_fixture(tmp_path)
    before = session_state(
        fixture["sessions"].get_session(fixture["session"].id)
    )

    fixture["builder"].build(fixture["session"].id)
    fixture["builder"].build(fixture["session"].id)

    assert session_state(
        fixture["sessions"].get_session(fixture["session"].id)
    ) == before


def test_session_decision_projection_emits_compact_diagnostic_event(
    tmp_path,
) -> None:
    fixture = make_session_projection_fixture(tmp_path)

    result = fixture["builder"].build(fixture["session"].id)

    events = fixture["events"].list_persisted_events(
        event_type="session_decision_projection_built"
    )
    assert len(events) == 1
    assert events[0].metadata == {
        "session_id": fixture["session"].id,
        "projection_count": result.projection_count,
        "source": SESSION_DECISION_PROJECTION_SOURCE,
    }
    assert "projections" not in events[0].metadata
