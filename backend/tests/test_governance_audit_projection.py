from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.runtime.projection_registry import ProjectionRegistry
from app.services.event_service import EventService, event_service
from app.services.governance_audit_projection_builder_service import (
    GovernanceAuditProjectionBuildError,
    GovernanceAuditProjectionBuilder,
)
from app.services.governance_audit_service import GovernanceAuditService
from app.services.projection_rebuild_service import ProjectionRebuildService
from app.services.trace_service import TraceService


BUILT_AT = datetime(2026, 6, 14, 18, 0, tzinfo=UTC)


def make_builder(tmp_path):
    events = EventService(TraceService(tmp_path / "governance_audit.db"))
    builder = GovernanceAuditProjectionBuilder(
        events=events,
        clock=lambda: BUILT_AT,
    )
    return builder, events


def emit_governance_events(events: EventService) -> None:
    events.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Recommendation selected",
        metadata={
            "decision_id": "decision-1",
            "decision_type": "recommendation_selection",
            "session_id": "session-1",
            "selected_entity_id": "recommendation-1",
        },
    )
    events.emit_event_sync(
        EventType.DECISION_EVIDENCE_CREATED,
        "Decision evidence",
        metadata={
            "decision_id": "decision-1",
            "evidence_id": "evidence-1",
        },
    )
    events.emit_event_sync(
        EventType.RUNTIME_GOVERNANCE_BLOCKED,
        "Runtime governance blocked",
        metadata={
            "task_id": "task-1",
            "decision": "block",
            "reasons": ["error_budget_exhausted"],
        },
    )
    events.emit_event_sync(
        EventType.REFLECTION_REQUESTED,
        "Reflection requested",
        metadata={
            "reflection_request_id": "reflection-1",
            "task_id": "task-1",
            "status": "pending",
            "reasons": ["governance_degraded"],
        },
    )
    events.emit_event_sync(
        EventType.PROPOSAL_RESOLVED,
        "Proposal approved",
        metadata={
            "proposal_id": "proposal-1",
            "status": "approved",
            "decision": "approve",
            "source_type": "planner_recommendation",
        },
    )
    events.emit_event_sync(
        EventType.PROPOSAL_RESOLVED,
        "Proposal rejected",
        metadata={
            "proposal_id": "proposal-2",
            "status": "rejected",
            "decision": "reject",
            "source_type": "manual",
        },
    )


def test_governance_audit_projection_build(tmp_path) -> None:
    builder, events = make_builder(tmp_path)
    emit_governance_events(events)

    projection = builder.build_read_only()

    assert projection.metadata.projection_type == (
        "governance_audit_projection"
    )
    assert projection.metadata.schema_version == 1
    assert projection.metadata.built_at == BUILT_AT
    assert [record.source_event_id for record in projection.records] == [
        1,
        3,
        4,
        5,
        6,
    ]
    decision = projection.records[0]
    assert decision.decision_id == "decision-1"
    assert decision.evidence_count == 1
    assert decision.outcome == "selected"
    assert projection.summary.total_decisions == 5
    assert projection.summary.approvals == 1
    assert projection.summary.rejections == 1
    assert projection.summary.policy_evaluations == 1
    assert projection.summary.reflection_triggers == 1
    assert projection.summary.budget_actions == 1
    assert projection.summary.governance_records_total == 5


def test_governance_audit_projection_rebuild_emits_diagnostics(
    tmp_path,
) -> None:
    builder, events = make_builder(tmp_path)
    emit_governance_events(events)
    registry = ProjectionRegistry()
    registry.register(builder)
    rebuilds = ProjectionRebuildService(
        registry=registry,
        events=events,
    )

    result = rebuilds.rebuild(
        "governance_audit_projection",
        "event_store",
    )

    assert result.projection_data.records[0].decision_id == "decision-1"
    assert len(
        events.list_persisted_events(
            event_type="governance_decision_recorded"
        )
    ) == 5
    assert len(
        events.list_persisted_events(
            event_type="governance_projection_updated"
        )
    ) == 1
    assert len(
        events.list_persisted_events(
            event_type="governance_projection_rebuilt"
        )
    ) == 1


def test_governance_audit_ordering_is_deterministic(tmp_path) -> None:
    builder, events = make_builder(tmp_path)
    emit_governance_events(events)
    service = GovernanceAuditService(builder)

    first = service.list_records()
    second = service.list_records()

    assert first == second
    assert [record.source_event_id for record in first] == [
        6,
        5,
        4,
        3,
        1,
    ]


def test_governance_audit_summary_metrics(tmp_path) -> None:
    builder, events = make_builder(tmp_path)
    emit_governance_events(events)

    summary = GovernanceAuditService(builder).summary()

    assert summary.model_dump() == {
        "governance_records_total": 5,
        "approvals_total": 1,
        "rejections_total": 1,
        "policy_evaluations_total": 1,
        "reflection_triggers_total": 1,
        "budget_actions_total": 1,
        "total_decisions": 5,
        "approvals": 1,
        "rejections": 1,
        "policy_evaluations": 1,
        "reflection_triggers": 1,
        "budget_actions": 1,
        "last_governance_activity_timestamp": (
            builder.build_read_only().records[-1].occurred_at
        ),
    }


def test_governance_audit_rejects_malformed_event(tmp_path) -> None:
    builder, events = make_builder(tmp_path)
    events.emit_event_sync(
        EventType.PROPOSAL_RESOLVED,
        "Malformed proposal",
        metadata={
            "proposal_id": "proposal-1",
            "status": "proposed",
        },
    )

    with pytest.raises(
        GovernanceAuditProjectionBuildError,
        match="proposal status must be approved or rejected",
    ):
        builder.build_read_only()


def test_governance_audit_rejects_missing_metadata(tmp_path) -> None:
    builder, events = make_builder(tmp_path)
    events.emit_event_sync(
        EventType.RUNTIME_GOVERNANCE_BLOCKED,
        "Missing task metadata",
        metadata={"decision": "block"},
    )

    with pytest.raises(
        GovernanceAuditProjectionBuildError,
        match="missing task_id",
    ):
        builder.build_read_only()


def test_governance_audit_routes_are_read_only() -> None:
    emit_governance_events(event_service)
    client = TestClient(app)

    audit = client.get("/runtime/governance/audit")
    decision_id = audit.json()[0]["decision_id"]
    detail = client.get(f"/runtime/governance/audit/{decision_id}")
    summary = client.get("/runtime/governance/summary")

    assert audit.status_code == 200
    source_event_ids = [
        record["source_event_id"] for record in audit.json()
    ]
    assert len(source_event_ids) == 5
    assert source_event_ids == sorted(source_event_ids, reverse=True)
    assert detail.status_code == 200
    assert detail.json()["decision_id"] == decision_id
    assert summary.status_code == 200
    assert summary.json()["governance_records_total"] == 5
    assert not event_service.list_persisted_events(
        event_type="governance_projection_updated"
    )


def test_governance_audit_detail_returns_not_found() -> None:
    response = TestClient(app).get(
        "/runtime/governance/audit/missing-decision"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Governance audit record not found: missing-decision"
        )
    }
