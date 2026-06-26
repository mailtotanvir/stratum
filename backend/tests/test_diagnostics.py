import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.db.schema import ProposalRecord, TaskRecord
from app.routes import diagnostics as diagnostics_routes
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService
from app.services.planner_recommendation_service import PlannerRecommendationService
from app.services.proposal_service import ProposalService
from app.services.reconstruction_service import ReconstructionService
from app.services.task_service import TaskService
from app.services.trace_service import TraceService


def make_diagnostics_services(tmp_path):
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    reconstruction = ReconstructionService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
    )
    diagnostics = DiagnosticsService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        reconstruction=reconstruction,
    )
    return events, tasks, proposals, diagnostics


def test_event_diagnostics_empty_event_store(tmp_path) -> None:
    service = DiagnosticsService(EventService(TraceService(tmp_path / "trace.db")))

    assert service.event_store_health() == {
        "total_events": 0,
        "event_type_counts": {},
        "lifecycle_event_counts": {
            "task_created": 0,
            "task_running": 0,
            "task_completed": 0,
            "task_failed": 0,
        },
        "missing_task_id_count": 0,
        "missing_task_id_by_type": {},
        "missing_proposal_id_by_type": {},
        "latest_event_timestamp": None,
        "latest_event_type": None,
    }


def test_event_diagnostics_event_type_counts(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = DiagnosticsService(events)

        await events.emit_event(EventType.TASK_CREATED, "Created", metadata={})
        await events.emit_event(EventType.TASK_CREATED, "Created again", metadata={})
        await events.emit_event(EventType.WARNING, "Warning", metadata={})

        health = service.event_store_health()

        assert health["total_events"] == 3
        assert health["event_type_counts"] == {
            "task_created": 2,
            "warning": 1,
        }

    asyncio.run(run_flow())


def test_event_diagnostics_lifecycle_counts_and_missing_task_id(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = DiagnosticsService(events)

        await events.emit_event(
            EventType.TASK_CREATED,
            "Created",
            metadata={"task_id": "task-1"},
        )
        await events.emit_event(
            EventType.TASK_RUNNING,
            "Running without task id",
            metadata={},
        )
        await events.emit_event(
            EventType.TASK_COMPLETED,
            "Completed",
            metadata={"task_id": "task-1"},
        )
        await events.emit_event(
            EventType.TASK_FAILED,
            "Failed with invalid task id",
            metadata={"task_id": None},
        )

        health = service.event_store_health()

        assert health["lifecycle_event_counts"] == {
            "task_created": 1,
            "task_running": 1,
            "task_completed": 1,
            "task_failed": 1,
        }
        assert health["missing_task_id_count"] == 2

    asyncio.run(run_flow())


def test_event_diagnostics_groups_missing_task_id_by_type(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = DiagnosticsService(events)

        await events.emit_event(EventType.TASK_CREATED, "Missing", metadata={})
        await events.emit_event(
            EventType.TASK_COMPLETED,
            "Missing",
            metadata={"task_id": None},
        )
        await events.emit_event(
            EventType.TASK_COMPLETED,
            "Present",
            metadata={"task_id": "task-1"},
        )
        await events.emit_event(EventType.WARNING, "No task id", metadata={})

        health = service.event_store_health()

        assert health["missing_task_id_count"] == 2
        assert health["missing_task_id_by_type"] == {
            "task_created": 1,
            "task_completed": 1,
        }

    asyncio.run(run_flow())


def test_event_diagnostics_groups_missing_proposal_id_by_type(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = DiagnosticsService(events)

        await events.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Missing",
            metadata={},
        )
        await events.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Missing",
            metadata={"proposal_id": None},
        )
        await events.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Present",
            metadata={"proposal_id": "proposal-1"},
        )
        await events.emit_event(EventType.WARNING, "No proposal id", metadata={})

        health = service.event_store_health()

        assert health["missing_proposal_id_by_type"] == {
            "proposal_generated": 1,
            "proposal_resolved": 1,
        }

    asyncio.run(run_flow())


def test_event_diagnostics_no_missing_ids_returns_empty_grouped_objects(
    tmp_path,
) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = DiagnosticsService(events)

        await events.emit_event(
            EventType.TASK_CREATED,
            "Task",
            metadata={"task_id": "task-1"},
        )
        await events.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Proposal",
            metadata={"proposal_id": "proposal-1"},
        )

        health = service.event_store_health()

        assert health["missing_task_id_count"] == 0
        assert health["missing_task_id_by_type"] == {}
        assert health["missing_proposal_id_by_type"] == {}
        assert "total_events" in health
        assert "event_type_counts" in health
        assert "lifecycle_event_counts" in health
        assert "latest_event_timestamp" in health
        assert "latest_event_type" in health

    asyncio.run(run_flow())


def test_event_diagnostics_latest_event_timestamp_and_type(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = DiagnosticsService(events)

        first = await events.emit_event(EventType.TASK_CREATED, "Created")
        latest = await events.emit_event(EventType.TASK_FAILED, "Failed")

        health = service.event_store_health()

        assert first.ts <= latest.ts
        assert health["latest_event_timestamp"] == latest.ts
        assert health["latest_event_type"] == "task_failed"

    asyncio.run(run_flow())


def test_event_diagnostics_endpoint(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics_routes.diagnostics_service = DiagnosticsService(
        EventService(trace_store)
    )
    client = TestClient(app)

    events.emit_event_sync(
        EventType.TASK_CREATED,
        "Created",
        metadata={"task_id": "task-1"},
    )

    response = client.get("/diagnostics/events")

    assert response.status_code == 200
    body = response.json()
    assert body["total_events"] == 1
    assert body["event_type_counts"] == {"task_created": 1}
    assert body["lifecycle_event_counts"]["task_created"] == 1
    assert body["missing_task_id_count"] == 0
    assert body["latest_event_type"] == "task_created"


def test_proposal_diagnostics_empty(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    proposals = ProposalService(tmp_path / "proposals.db")
    service = DiagnosticsService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    assert service.proposal_health() == {
        "total_proposals": 0,
        "status_counts": {
            "proposed": 0,
            "approved": 0,
            "rejected": 0,
        },
        "source_type_counts": {
            "manual": 0,
            "planner_recommendation": 0,
        },
        "proposals_with_source_context_snapshot": 0,
        "proposals_missing_source_context_snapshot": 0,
        "proposal_source_context_snapshot_version_counts": {},
        "proposals_with_legacy_or_unknown_source_context_snapshot": 0,
        "sources": [],
        "event_counts": {
            "proposal_generated": 0,
            "proposal_resolved": 0,
        },
        "event_source_type_counts": {
            "manual": 0,
            "planner_recommendation": 0,
        },
        "unresolved_count": 0,
        "missing_proposal_id_count": 0,
        "missing_proposal_id_by_type": {},
        "latest_proposal_event_timestamp": None,
        "latest_proposal_event_type": None,
    }


def test_proposal_diagnostics_status_counts_and_unresolved_count(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = DiagnosticsService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    proposed = proposals.create_proposal("Proposed", "Body")
    approved = proposals.create_proposal("Approved", "Body")
    rejected = proposals.create_proposal("Rejected", "Body")
    proposals.respond(approved.id, "approve")
    proposals.respond(rejected.id, "reject")

    health = service.proposal_health()

    assert proposed.status == "proposed"
    assert health["total_proposals"] == 3
    assert health["status_counts"] == {
        "proposed": 1,
        "approved": 1,
        "rejected": 1,
    }
    assert health["source_type_counts"] == {
        "manual": 3,
        "planner_recommendation": 0,
    }
    assert health["unresolved_count"] == 1


def test_proposal_diagnostics_lifecycle_event_counts(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = DiagnosticsService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    first = proposals.create_proposal("First", "Body")
    second = proposals.create_proposal("Second", "Body")
    proposals.respond(first.id, "approve")
    proposals.respond(second.id, "reject")

    health = service.proposal_health()

    assert health["event_counts"] == {
        "proposal_generated": 2,
        "proposal_resolved": 2,
    }
    assert health["event_source_type_counts"] == {
        "manual": 4,
        "planner_recommendation": 0,
    }


def test_proposal_diagnostics_includes_source_lineage(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = DiagnosticsService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    manual = proposals.create_proposal("Manual", "Body")
    planner = proposals.create_proposal(
        "Planner",
        "Body",
        source_type="planner_recommendation",
        source_id="recommendation-1",
    )
    planner_with_snapshot = proposals.create_proposal(
        "Planner with snapshot",
        "Body",
        source_type="planner_recommendation",
        source_id="recommendation-2",
        source_context_snapshot={
            "schema_version": 1,
            "available_tool_count": 1,
        },
    )
    planner_with_legacy_snapshot = proposals.create_proposal(
        "Planner with legacy snapshot",
        "Body",
        source_type="planner_recommendation",
        source_id="recommendation-3",
        source_context_snapshot={"available_tool_count": 1},
    )

    health = service.proposal_health()
    sources = {source["proposal_id"]: source for source in health["sources"]}

    assert health["source_type_counts"] == {
        "manual": 1,
        "planner_recommendation": 3,
    }
    assert health["event_source_type_counts"] == {
        "manual": 1,
        "planner_recommendation": 3,
    }
    assert health["proposals_with_source_context_snapshot"] == 2
    assert health["proposals_missing_source_context_snapshot"] == 1
    assert health["proposal_source_context_snapshot_version_counts"] == {
        "1": 1,
        "legacy_or_unknown": 1,
    }
    assert (
        health["proposals_with_legacy_or_unknown_source_context_snapshot"]
        == 1
    )
    assert sources[manual.id] == {
        "proposal_id": manual.id,
        "source_type": "manual",
        "source_id": None,
    }
    assert sources[planner.id] == {
        "proposal_id": planner.id,
        "source_type": "planner_recommendation",
        "source_id": "recommendation-1",
        "recommendation_id": "recommendation-1",
    }
    assert sources[planner_with_snapshot.id] == {
        "proposal_id": planner_with_snapshot.id,
        "source_type": "planner_recommendation",
        "source_id": "recommendation-2",
        "recommendation_id": "recommendation-2",
    }
    assert sources[planner_with_legacy_snapshot.id] == {
        "proposal_id": planner_with_legacy_snapshot.id,
        "source_type": "planner_recommendation",
        "source_id": "recommendation-3",
        "recommendation_id": "recommendation-3",
    }


def test_proposal_diagnostics_missing_proposal_id_count(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        proposals = ProposalService(tmp_path / "proposals.db", events=events)
        service = DiagnosticsService(events=events, proposals=proposals)

        await events.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Missing proposal id",
            metadata={},
        )
        await events.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Invalid proposal id",
            metadata={"proposal_id": None},
        )
        await events.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Valid proposal id",
            metadata={"proposal_id": "proposal-1"},
        )

        health = service.proposal_health()

        assert health["event_counts"] == {
            "proposal_generated": 1,
            "proposal_resolved": 2,
        }
        assert health["missing_proposal_id_count"] == 2
        assert health["missing_proposal_id_by_type"] == {
            "proposal_generated": 1,
            "proposal_resolved": 1,
        }

    asyncio.run(run_flow())


def test_proposal_diagnostics_latest_event_timestamp_and_type(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        proposals = ProposalService(tmp_path / "proposals.db", events=events)
        service = DiagnosticsService(events=events, proposals=proposals)

        first = await events.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Generated",
            metadata={"proposal_id": "proposal-1"},
        )
        latest = await events.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Resolved",
            metadata={"proposal_id": "proposal-1"},
        )

        health = service.proposal_health()

        assert first.ts <= latest.ts
        assert health["latest_proposal_event_timestamp"] == latest.ts
        assert health["latest_proposal_event_type"] == "proposal_resolved"

    asyncio.run(run_flow())


def test_proposal_diagnostics_endpoint(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    diagnostics_routes.diagnostics_service = DiagnosticsService(
        events=EventService(trace_store),
        proposals=proposals,
    )
    client = TestClient(app)

    created = proposals.create_proposal("Endpoint proposal", "Body")
    proposals.respond(created.id, "approve")

    response = client.get("/diagnostics/proposals")

    assert response.status_code == 200
    body = response.json()
    assert body["total_proposals"] == 1
    assert body["status_counts"] == {
        "proposed": 0,
        "approved": 1,
        "rejected": 0,
    }
    assert body["source_type_counts"] == {
        "manual": 1,
        "planner_recommendation": 0,
    }
    assert body["sources"] == [
        {
            "proposal_id": created.id,
            "source_type": "manual",
            "source_id": None,
        }
    ]
    assert body["event_counts"] == {
        "proposal_generated": 1,
        "proposal_resolved": 1,
    }
    assert body["event_source_type_counts"] == {
        "manual": 2,
        "planner_recommendation": 0,
    }
    assert body["unresolved_count"] == 0
    assert body["missing_proposal_id_count"] == 0
    assert body["missing_proposal_id_by_type"] == {}
    assert body["latest_proposal_event_type"] == "proposal_resolved"


def diagnostics_tool() -> Tool:
    return Tool(
        id="tool-1",
        name="shell.read",
        description="Read a file.",
        enabled=True,
        created_at="2026-06-05T00:00:00+00:00",
        updated_at="2026-06-05T00:00:00+00:00",
        parameters=[],
    )


def create_diagnostics_recommendation(
    recommendations: PlannerRecommendationService,
    session_id: str,
    governance_status: str = "ok",
    context_snapshot: dict | None = None,
):
    return recommendations.create_recommendation(
        PlannerRequest(
            task_id=f"task-{session_id}",
            session_id=session_id,
            objective=f"Objective {session_id}",
            available_tools=[diagnostics_tool()],
            context={},
        ),
        PlannerResponse(
            proposed_tool=diagnostics_tool(),
            rationale="Selected first enabled tool: shell.read",
            confidence=0.75,
        ),
        {"governance_status": governance_status},
        context_snapshot=context_snapshot,
    )


def test_planner_recommendation_diagnostics_counts_and_sessions(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    recommendations = PlannerRecommendationService(
        tmp_path / "recommendations.db",
        events=events,
    )
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    reconstruction = ReconstructionService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
    )
    service = DiagnosticsService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
        reconstruction=reconstruction,
    )

    first = create_diagnostics_recommendation(
        recommendations,
        "session-1",
        "ok",
        context_snapshot={
            "schema_version": 1,
            "active_proposal_count": 0,
            "active_recommendation_count": 0,
            "available_tool_count": 1,
            "recent_event_count": 0,
            "diagnostics_summary": {},
        },
    )
    second = create_diagnostics_recommendation(
        recommendations,
        "session-1",
        "degraded",
        context_snapshot={"available_tool_count": 1},
    )
    third = create_diagnostics_recommendation(recommendations, "session-2", "ok")
    recommendations.mark_promoted(first.id)
    asyncio.run(recommendations.dismiss(third.id))
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        "Recommendation promoted",
        metadata={
            "recommendation_id": first.id,
            "proposal_id": "proposal-1",
            "task_id": first.task_id,
            "session_id": first.session_id,
        },
    )

    health = service.planner_recommendation_health()

    assert health["total_recommendations"] == 3
    assert health["recommendation_context_snapshot_count"] == 2
    assert health["recommendations_missing_context_snapshot"] == 1
    assert health["recommendation_context_snapshot_version_counts"] == {
        "1": 1,
        "legacy_or_unknown": 1,
    }
    assert (
        health["recommendations_with_legacy_or_unknown_context_snapshot"]
        == 1
    )
    assert health["governance_status_counts"] == {
        "ok": 2,
        "degraded": 1,
    }
    assert health["planner_recommendation_status_counts"] == {
        "active": 1,
        "promoted": 1,
        "dismissed": 1,
    }
    assert health["promoted_count"] == 1
    assert health["unpromoted_count"] == 2
    assert health["by_session_id"] == {
        "session-1": [first.id, second.id],
        "session-2": [third.id],
    }
    assert health["consistency"]["consistent"] is True


def test_planner_recommendation_diagnostics_detects_missing_promotion_reference(
    tmp_path,
) -> None:
    events = EventService(TraceService(tmp_path / "trace.db"))
    service = DiagnosticsService(events=events)

    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        "Missing recommendation promoted",
        metadata={
            "recommendation_id": "missing-recommendation",
            "proposal_id": "proposal-1",
            "task_id": "task-1",
            "session_id": "session-1",
        },
    )

    health = service.planner_recommendation_health()

    assert health["total_recommendations"] == 0
    assert health["recommendation_context_snapshot_count"] == 0
    assert health["recommendations_missing_context_snapshot"] == 0
    assert health["recommendation_context_snapshot_version_counts"] == {}
    assert (
        health["recommendations_with_legacy_or_unknown_context_snapshot"]
        == 0
    )
    assert health["planner_recommendation_status_counts"] == {
        "active": 0,
        "promoted": 0,
        "dismissed": 0,
    }
    assert health["consistency"]["consistent"] is False
    assert health["consistency"]["missing_promotion_references"] == [
        "missing-recommendation"
    ]
    assert health["missing_recommendation_lifecycle_reference_count"] == 1
    assert health["invalid_recommendation_status_transition_count"] == 0
    assert health["duplicate_recommendation_terminal_event_count"] == 0


def test_planner_recommendation_diagnostics_exposes_lifecycle_issues(
    tmp_path,
) -> None:
    events = EventService(TraceService(tmp_path / "trace.db"))
    service = DiagnosticsService(
        events=events,
        reconstruction=ReconstructionService(events=events),
    )
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_CREATED,
        "Created",
        metadata={"recommendation_id": "recommendation-1"},
    )
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_DISMISSED,
        "Dismissed",
        metadata={"recommendation_id": "recommendation-1"},
    )
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_DISMISSED,
        "Dismissed again",
        metadata={"recommendation_id": "recommendation-1"},
    )
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        "Promoted after dismissal",
        metadata={"recommendation_id": "recommendation-1"},
    )

    health = service.planner_recommendation_health()

    assert health["invalid_recommendation_status_transition_count"] == 1
    assert health["missing_recommendation_lifecycle_reference_count"] == 0
    assert health["duplicate_recommendation_terminal_event_count"] == 1
    assert [issue["issue_type"] for issue in health["recommendation_lifecycle_issues"]] == [
        "duplicate_terminal_event",
        "invalid_status_transition",
    ]


def test_planner_recommendation_diagnostics_endpoint(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    recommendations = PlannerRecommendationService(
        tmp_path / "recommendations.db",
        events=events,
    )
    diagnostics_routes.diagnostics_service = DiagnosticsService(
        events=EventService(trace_store),
        recommendations=recommendations,
        reconstruction=ReconstructionService(
            events=EventService(trace_store),
            recommendations=recommendations,
        ),
    )
    create_diagnostics_recommendation(recommendations, "session-1", "ok")
    client = TestClient(app)

    response = client.get("/diagnostics/planner-recommendations")

    assert response.status_code == 200
    assert response.json()["total_recommendations"] == 1
    assert response.json()["recommendation_context_snapshot_count"] == 0
    assert response.json()["recommendations_missing_context_snapshot"] == 1
    assert response.json()["recommendation_context_snapshot_version_counts"] == {}
    assert (
        response.json()[
            "recommendations_with_legacy_or_unknown_context_snapshot"
        ]
        == 0
    )
    assert response.json()["governance_status_counts"] == {"ok": 1}
    assert response.json()["planner_recommendation_status_counts"] == {
        "active": 1,
        "promoted": 0,
        "dismissed": 0,
    }


def test_diagnostics_summary_empty(tmp_path) -> None:
    _, _, _, service = make_diagnostics_services(tmp_path)

    assert service.runtime_summary() == {
        "decision_record_count": 0,
        "decision_evidence_count": 0,
        "decision_trail_count": 0,
        "events": {
            "total_events": 0,
            "latest_event_timestamp": None,
            "latest_event_type": None,
        },
        "tasks": {
            "total_tasks": 0,
            "status_counts": {
                "created": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
            },
            "inconsistent": 0,
        },
        "proposals": {
            "total_proposals": 0,
            "status_counts": {
                "proposed": 0,
                "approved": 0,
                "rejected": 0,
            },
            "source_type_counts": {
                "manual": 0,
                "planner_recommendation": 0,
            },
            "unresolved_count": 0,
            "inconsistent": 0,
        },
        "planner_recommendations": {
            "planner_recommendation_count": 0,
            "active_recommendation_count": 0,
            "planner_recommendation_promoted_count": 0,
            "dismissed_recommendation_count": 0,
            "planner_recommendation_unpromoted_count": 0,
        },
        "integrity": {
            "missing_task_id_count": 0,
            "missing_proposal_id_count": 0,
        },
        "governance": {
            "severity_counts": {
                "info": 0,
                "warning": 0,
                "error": 0,
                "critical": 0,
            },
            "highest_severity": None,
            "has_critical": False,
            "status": "ok",
            "error_budget": {
                "status": "within_budget",
            },
        },
        "evaluations": {
            "projection_count": 8,
            "healthy_projections": 8,
            "unhealthy_projections": 0,
            "dependency_failures": 0,
            "overall_health": "healthy",
        },
        "evaluation_reconstruction": {
            "projections_rebuildable": 5,
            "successful_reconstructions": 0,
            "failed_reconstructions": 0,
            "replay_validation_status": "not_verified",
        },
    }


def test_diagnostics_summary_with_task_proposal_and_event_data(tmp_path) -> None:
    _, tasks, proposals, service = make_diagnostics_services(tmp_path)

    task = tasks.create_task("Summary task")
    tasks.mark_completed(task.id)
    proposal = proposals.create_proposal("Summary proposal", "Body", task_id=task.id)
    proposals.respond(proposal.id, "approve")

    summary = service.runtime_summary()

    assert summary["events"]["total_events"] == 4
    assert summary["events"]["latest_event_type"] == "proposal_resolved"
    assert summary["events"]["latest_event_timestamp"] is not None
    assert summary["tasks"] == {
        "total_tasks": 1,
        "status_counts": {
            "created": 0,
            "running": 0,
            "completed": 1,
            "failed": 0,
        },
        "inconsistent": 0,
    }
    assert summary["proposals"] == {
        "total_proposals": 1,
        "status_counts": {
            "proposed": 0,
            "approved": 1,
            "rejected": 0,
        },
        "source_type_counts": {
            "manual": 1,
            "planner_recommendation": 0,
        },
        "unresolved_count": 0,
        "inconsistent": 0,
    }
    assert summary["planner_recommendations"] == {
        "planner_recommendation_count": 0,
        "active_recommendation_count": 0,
        "planner_recommendation_promoted_count": 0,
        "dismissed_recommendation_count": 0,
        "planner_recommendation_unpromoted_count": 0,
    }


def test_diagnostics_summary_includes_planner_recommendation_counts(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    recommendations = PlannerRecommendationService(
        tmp_path / "recommendations.db",
        events=events,
    )
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    reconstruction = ReconstructionService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
    )
    service = DiagnosticsService(
        events=EventService(trace_store),
        tasks=tasks,
        proposals=proposals,
        recommendations=recommendations,
        reconstruction=reconstruction,
    )
    promoted = create_diagnostics_recommendation(recommendations, "session-1")
    create_diagnostics_recommendation(recommendations, "session-2")
    recommendations.mark_promoted(promoted.id)
    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        "Recommendation promoted",
        metadata={
            "recommendation_id": promoted.id,
            "proposal_id": "proposal-1",
            "task_id": promoted.task_id,
            "session_id": promoted.session_id,
        },
    )

    assert service.runtime_summary()["planner_recommendations"] == {
        "planner_recommendation_count": 2,
        "active_recommendation_count": 1,
        "planner_recommendation_promoted_count": 1,
        "dismissed_recommendation_count": 0,
        "planner_recommendation_unpromoted_count": 1,
    }


def test_diagnostics_summary_includes_existing_top_level_fields(tmp_path) -> None:
    _, _, _, service = make_diagnostics_services(tmp_path)

    assert set(service.runtime_summary()) == {
        "decision_record_count",
        "decision_evidence_count",
        "decision_trail_count",
        "events",
        "tasks",
        "proposals",
        "planner_recommendations",
        "integrity",
        "governance",
        "evaluations",
        "evaluation_reconstruction",
    }


def test_diagnostics_summary_reflects_inconsistent_task_and_proposal_counts(
    tmp_path,
) -> None:
    _, tasks, proposals, service = make_diagnostics_services(tmp_path)

    task = tasks.create_task("Drifting task")
    tasks.mark_completed(task.id)
    proposal = proposals.create_proposal("Drifting proposal", "Body")
    proposals.respond(proposal.id, "approve")

    with tasks.session_factory() as session:
        record = session.get(TaskRecord, task.id)
        record.status = "running"
        session.commit()
    with proposals.session_factory() as session:
        record = session.get(ProposalRecord, proposal.id)
        record.status = "rejected"
        session.commit()

    summary = service.runtime_summary()

    assert summary["tasks"]["inconsistent"] == 1
    assert summary["proposals"]["inconsistent"] == 1


def test_diagnostics_summary_reflects_missing_metadata_counts(tmp_path) -> None:
    async def run_flow() -> None:
        events, _, _, service = make_diagnostics_services(tmp_path)

        await events.emit_event(EventType.TASK_CREATED, "Missing task", metadata={})
        await events.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Missing proposal",
            metadata={},
        )

        summary = service.runtime_summary()

        assert summary["integrity"] == {
            "missing_task_id_count": 1,
            "missing_proposal_id_count": 1,
        }

    asyncio.run(run_flow())


def test_diagnostics_summary_includes_severity_counts(tmp_path) -> None:
    events, _, _, service = make_diagnostics_services(tmp_path)

    events.emit_event_sync(EventType.TASK_CREATED, "Created")
    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")
    events.emit_event_sync(EventType.ERROR, "Error", severity="error")

    assert service.runtime_summary()["governance"]["severity_counts"] == {
        "info": 1,
        "warning": 1,
        "error": 1,
        "critical": 0,
    }


def test_diagnostics_summary_reflects_highest_severity(tmp_path) -> None:
    events, _, _, service = make_diagnostics_services(tmp_path)

    events.emit_event_sync(EventType.TASK_CREATED, "Created")
    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")

    assert service.runtime_summary()["governance"]["highest_severity"] == "warning"


def test_diagnostics_summary_reflects_critical_event(tmp_path) -> None:
    events, _, _, service = make_diagnostics_services(tmp_path)

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    assert service.runtime_summary()["governance"]["has_critical"] is True
    assert service.runtime_summary()["governance"]["status"] == "critical"


def test_diagnostics_summary_includes_compact_error_budget_status(
    tmp_path,
) -> None:
    events, _, _, service = make_diagnostics_services(tmp_path)

    for index in range(6):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    assert service.runtime_summary()["governance"]["error_budget"] == {
        "status": "budget_exhausted",
    }


def test_diagnostics_summary_status_matches_governance_health(tmp_path) -> None:
    events, _, _, service = make_diagnostics_services(tmp_path)
    diagnostics_routes.diagnostics_service = service
    client = TestClient(app)

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")

    summary = client.get("/diagnostics/summary")
    governance = client.get("/diagnostics/governance")

    assert summary.status_code == 200
    assert governance.status_code == 200
    assert summary.json()["governance"]["status"] == governance.json()["status"]


def test_diagnostics_summary_endpoint(tmp_path) -> None:
    _, tasks, proposals, service = make_diagnostics_services(tmp_path)
    diagnostics_routes.diagnostics_service = service
    client = TestClient(app)

    task = tasks.create_task("Endpoint task")
    proposals.create_proposal("Endpoint proposal", "Body", task_id=task.id)

    response = client.get("/diagnostics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["events"]["total_events"] == 2
    assert body["tasks"]["total_tasks"] == 1
    assert body["proposals"]["total_proposals"] == 1
    assert body["proposals"]["unresolved_count"] == 1
