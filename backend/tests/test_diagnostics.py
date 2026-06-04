import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.db.schema import ProposalRecord, TaskRecord
from app.routes import diagnostics as diagnostics_routes
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService
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
        "event_counts": {
            "proposal_generated": 0,
            "proposal_resolved": 0,
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
    assert body["event_counts"] == {
        "proposal_generated": 1,
        "proposal_resolved": 1,
    }
    assert body["unresolved_count"] == 0
    assert body["missing_proposal_id_count"] == 0
    assert body["missing_proposal_id_by_type"] == {}
    assert body["latest_proposal_event_type"] == "proposal_resolved"


def test_diagnostics_summary_empty(tmp_path) -> None:
    _, _, _, service = make_diagnostics_services(tmp_path)

    assert service.runtime_summary() == {
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
            "unresolved_count": 0,
            "inconsistent": 0,
        },
        "integrity": {
            "missing_task_id_count": 0,
            "missing_proposal_id_count": 0,
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
        "unresolved_count": 0,
        "inconsistent": 0,
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
