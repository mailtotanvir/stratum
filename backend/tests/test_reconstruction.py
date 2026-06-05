import asyncio

from fastapi.testclient import TestClient

from app.db.schema import ProposalRecord, TaskRecord
from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.runtime_event import EventType
from app.models.task import TaskStatus
from app.models.tool import Tool
from app.routes import reconstruct as reconstruct_routes
from app.services.event_service import EventService
from app.services.planner_recommendation_service import PlannerRecommendationService
from app.services.proposal_service import ProposalService
from app.services.reconstruction_service import ReconstructionService
from app.services.task_service import TaskService
from app.services.trace_service import TraceService


def test_reconstruct_single_task_from_lifecycle_events(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    created = tasks.create_task("Rebuild one")
    tasks.mark_running(created.id)
    completed = tasks.mark_completed(created.id, summary="Finished")

    reconstructed = service.reconstruct_task_state(created.id)

    assert reconstructed == {
        "id": created.id,
        "found": True,
        "title": "Rebuild one",
        "status": "completed",
        "created_at": completed.created_at.isoformat(),
        "completed_at": completed.completed_at.isoformat(),
        "summary": "Finished",
    }


def test_reconstruct_multiple_tasks(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    first = tasks.create_task("First reconstructed")
    second = tasks.create_task("Second reconstructed")
    tasks.mark_completed(first.id)
    tasks.mark_failed(second.id, summary="Failed")

    reconstructed = service.reconstruct_all_task_states()
    by_id = {task["id"]: task for task in reconstructed}

    assert list(by_id) == [first.id, second.id]
    assert by_id[first.id]["status"] == "completed"
    assert by_id[second.id]["status"] == "failed"
    assert by_id[second.id]["summary"] == "Failed"


def test_compare_consistent_task_record_to_events(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    created = tasks.create_task("Consistent task")
    tasks.mark_completed(created.id, summary="Consistent")

    comparison = service.compare_task_record_to_events(created.id)

    assert comparison["task_id"] == created.id
    assert comparison["consistent"] is True
    assert comparison["differences"] == []
    assert comparison["record"] == comparison["reconstructed"]


def test_compare_detects_task_record_status_inconsistency(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    created = tasks.create_task("Inconsistent task")
    tasks.mark_completed(created.id)

    with tasks.session_factory() as session:
        record = session.get(TaskRecord, created.id)
        record.status = TaskStatus.RUNNING.value
        session.commit()

    comparison = service.compare_task_record_to_events(created.id)

    assert comparison["consistent"] is False
    assert comparison["differences"] == ["status"]
    assert comparison["record"]["status"] == "running"
    assert comparison["reconstructed"]["status"] == "completed"


def test_reconstruction_api_endpoints(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    reconstruct_routes.reconstruction_service = ReconstructionService(
        events=EventService(trace_store),
        tasks=tasks,
    )
    client = TestClient(app)

    created = tasks.create_task("API reconstructed")

    assert client.get("/reconstruct/tasks").json()[0]["id"] == created.id
    assert client.get(f"/reconstruct/tasks/{created.id}").json()["id"] == created.id
    comparison = client.get(f"/reconstruct/tasks/{created.id}/compare").json()
    assert comparison["consistent"] is True


def test_task_consistency_health_empty_task_table(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    tasks = TaskService(tmp_path / "tasks.db", events=EventService(trace_store))
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    assert service.task_consistency_health() == {
        "checked": 0,
        "consistent": 0,
        "inconsistent": 0,
        "items": [],
    }


def test_task_consistency_health_all_tasks_consistent(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    first = tasks.create_task("Consistent first")
    second = tasks.create_task("Consistent second")
    tasks.mark_completed(first.id)
    tasks.mark_failed(second.id, summary="Failed consistently")

    health = service.task_consistency_health()

    assert health["checked"] == 2
    assert health["consistent"] == 2
    assert health["inconsistent"] == 0
    assert [
        {
            "task_id": item["task_id"],
            "consistent": item["consistent"],
            "differences": item["differences"],
        }
        for item in health["items"]
    ] == [
        {"task_id": second.id, "consistent": True, "differences": []},
        {"task_id": first.id, "consistent": True, "differences": []},
    ]


def test_task_consistency_health_detects_one_inconsistent_task(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    service = ReconstructionService(events=EventService(trace_store), tasks=tasks)

    consistent = tasks.create_task("Still consistent")
    inconsistent = tasks.create_task("Will drift")
    tasks.mark_completed(consistent.id)
    tasks.mark_completed(inconsistent.id)

    with tasks.session_factory() as session:
        record = session.get(TaskRecord, inconsistent.id)
        record.status = TaskStatus.RUNNING.value
        session.commit()

    health = service.task_consistency_health()

    assert health["checked"] == 2
    assert health["consistent"] == 1
    assert health["inconsistent"] == 1
    assert health["items"] == [
        {"task_id": inconsistent.id, "consistent": False, "differences": ["status"]},
        {"task_id": consistent.id, "consistent": True, "differences": []},
    ]


def test_task_consistency_endpoint_returns_aggregate_counts(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    tasks = TaskService(tmp_path / "tasks.db", events=events)
    reconstruct_routes.reconstruction_service = ReconstructionService(
        events=EventService(trace_store),
        tasks=tasks,
    )
    client = TestClient(app)

    created = tasks.create_task("Endpoint consistency")

    response = client.get("/reconstruct/tasks/consistency")

    assert response.status_code == 200
    assert response.json() == {
        "checked": 1,
        "consistent": 1,
        "inconsistent": 0,
        "items": [
            {"task_id": created.id, "consistent": True, "differences": []},
        ],
    }


def test_reconstruct_single_proposal_from_lifecycle_events(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    created = proposals.create_proposal(
        "Rebuild proposal",
        "Proposal body",
        task_id="task-1",
    )
    resolved = proposals.respond(created.id, "approve")

    reconstructed = service.reconstruct_proposal_state(created.id)

    assert reconstructed == {
        "id": created.id,
        "found": True,
        "task_id": "task-1",
        "source_type": "manual",
        "source_id": None,
        "title": "Rebuild proposal",
        "body": "Proposal body",
        "status": "approved",
        "created_at": resolved.created_at.isoformat(),
        "resolved_at": resolved.resolved_at.isoformat(),
        "decision": "approve",
    }


def test_reconstruct_multiple_proposals(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    first = proposals.create_proposal("First proposal", "Body", task_id="task-1")
    second = proposals.create_proposal("Second proposal", "Body", task_id="task-2")
    proposals.respond(first.id, "approve")
    proposals.respond(second.id, "reject")

    reconstructed = service.reconstruct_all_proposal_states()
    by_id = {proposal["id"]: proposal for proposal in reconstructed}

    assert list(by_id) == [first.id, second.id]
    assert by_id[first.id]["status"] == "approved"
    assert by_id[first.id]["decision"] == "approve"
    assert by_id[second.id]["status"] == "rejected"
    assert by_id[second.id]["decision"] == "reject"


def test_reconstruct_planner_recommendation_source_lineage(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    created = proposals.create_proposal(
        "Planner proposal",
        "Body",
        source_type="planner_recommendation",
        source_id="recommendation-1",
    )

    reconstructed = service.reconstruct_proposal_state(created.id)

    assert reconstructed["source_type"] == "planner_recommendation"
    assert reconstructed["source_id"] == "recommendation-1"


def test_reconstruct_legacy_proposal_event_defaults_to_manual_source(
    tmp_path,
) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = ReconstructionService(events=events)

        await events.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Legacy proposal",
            metadata={
                "proposal_id": "proposal-1",
                "title": "Legacy proposal",
                "body": "Body",
                "status": "proposed",
                "created_at": "2026-06-05T00:00:00+00:00",
            },
        )

        reconstructed = service.reconstruct_proposal_state("proposal-1")

        assert reconstructed["source_type"] == "manual"
        assert reconstructed["source_id"] is None

    asyncio.run(run_flow())


def planner_tool(tool_id: str = "tool-1") -> Tool:
    return Tool(
        id=tool_id,
        name="shell.read",
        description="Read a file.",
        enabled=True,
        created_at="2026-06-05T00:00:00+00:00",
        updated_at="2026-06-05T00:00:00+00:00",
        parameters=[],
    )


def test_reconstruct_planner_recommendation_from_event_history(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    recommendations = PlannerRecommendationService(
        tmp_path / "recommendations.db",
        events=events,
    )
    service = ReconstructionService(
        events=EventService(trace_store),
        recommendations=recommendations,
    )
    request = PlannerRequest(
        task_id="task-1",
        session_id="session-1",
        objective="Inspect README",
        available_tools=[planner_tool()],
        context={},
    )
    response = PlannerResponse(
        proposed_tool=planner_tool(),
        rationale="Selected first enabled tool: shell.read",
        confidence=0.75,
    )

    created = recommendations.create_recommendation(
        request,
        response,
        {"governance_status": "ok"},
    )
    reconstructed = service.get_recommendation_lineage(created.id)

    assert reconstructed["recommendation_id"] == created.id
    assert reconstructed["found"] is True
    assert reconstructed["task_id"] == "task-1"
    assert reconstructed["session_id"] == "session-1"
    assert reconstructed["objective"] == "Inspect README"
    assert reconstructed["proposed_tool"]["name"] == "shell.read"
    assert reconstructed["rationale"] == "Selected first enabled tool: shell.read"
    assert reconstructed["confidence"] == 0.75
    assert reconstructed["governance_status"] == "ok"
    assert reconstructed["created_at"] == created.created_at.isoformat()
    assert reconstructed["promoted"] is False
    assert reconstructed["proposal_id"] is None


def test_reconstruct_promoted_planner_recommendation_has_proposal_id(
    tmp_path,
) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = ReconstructionService(events=events)

        await events.emit_event(
            EventType.PLANNER_RECOMMENDATION_CREATED,
            "Recommendation created",
            metadata={
                "recommendation_id": "recommendation-1",
                "task_id": "task-1",
                "session_id": "session-1",
                "objective": "Inspect README",
                "proposed_tool": {"name": "shell.read"},
                "rationale": "Selected first enabled tool: shell.read",
                "confidence": 0.75,
                "governance_status": "ok",
                "created_at": "2026-06-05T00:00:00+00:00",
            },
        )
        await events.emit_event(
            EventType.PLANNER_RECOMMENDATION_PROMOTED,
            "Recommendation promoted",
            metadata={
                "recommendation_id": "recommendation-1",
                "proposal_id": "proposal-1",
                "task_id": "task-1",
                "session_id": "session-1",
                "proposed_tool": {"name": "shell.read"},
            },
        )

        reconstructed = service.get_recommendation_lineage("recommendation-1")

        assert reconstructed["promoted"] is True
        assert reconstructed["proposal_id"] == "proposal-1"

    asyncio.run(run_flow())


def test_reconstruct_missing_recommendation_promotion_reference(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))
        service = ReconstructionService(events=events)

        await events.emit_event(
            EventType.PLANNER_RECOMMENDATION_PROMOTED,
            "Missing recommendation promoted",
            metadata={
                "recommendation_id": "missing-recommendation",
                "proposal_id": "proposal-1",
                "task_id": "task-1",
                "session_id": "session-1",
            },
        )

        reconstructed = service.get_recommendation_lineage("missing-recommendation")
        consistency = service.recommendation_consistency_health()

        assert reconstructed["found"] is False
        assert reconstructed["promoted"] is True
        assert reconstructed["proposal_id"] == "proposal-1"
        assert consistency["consistent"] is False
        assert consistency["missing_promotion_references"] == [
            "missing-recommendation"
        ]

    asyncio.run(run_flow())


def test_compare_consistent_proposal_record_to_events(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    created = proposals.create_proposal("Consistent proposal", "Body")
    proposals.respond(created.id, "approve")

    comparison = service.compare_proposal_record_to_events(created.id)

    assert comparison["proposal_id"] == created.id
    assert comparison["consistent"] is True
    assert comparison["differences"] == []
    assert comparison["record"] == comparison["reconstructed"]


def test_compare_detects_proposal_record_status_inconsistency(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )

    created = proposals.create_proposal("Inconsistent proposal", "Body")
    proposals.respond(created.id, "approve")

    with proposals.session_factory() as session:
        record = session.get(ProposalRecord, created.id)
        record.status = "rejected"
        session.commit()

    comparison = service.compare_proposal_record_to_events(created.id)

    assert comparison["consistent"] is False
    assert comparison["differences"] == ["status"]
    assert comparison["record"]["status"] == "rejected"
    assert comparison["reconstructed"]["status"] == "approved"


def test_proposal_consistency_endpoint_aggregates_counts(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    reconstruct_routes.reconstruction_service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )
    client = TestClient(app)

    consistent = proposals.create_proposal("Consistent proposal", "Body")
    inconsistent = proposals.create_proposal("Inconsistent proposal", "Body")
    proposals.respond(consistent.id, "approve")
    proposals.respond(inconsistent.id, "approve")

    with proposals.session_factory() as session:
        record = session.get(ProposalRecord, inconsistent.id)
        record.status = "rejected"
        session.commit()

    response = client.get("/reconstruct/proposals/consistency")

    assert response.status_code == 200
    assert response.json() == {
        "checked": 2,
        "consistent": 1,
        "inconsistent": 1,
        "items": [
            {
                "proposal_id": inconsistent.id,
                "consistent": False,
                "differences": ["status"],
            },
            {
                "proposal_id": consistent.id,
                "consistent": True,
                "differences": [],
            },
        ],
    }


def test_missing_proposal_reconstruction_returns_found_false(tmp_path) -> None:
    service = ReconstructionService(
        events=EventService(TraceService(tmp_path / "trace.db"))
    )

    assert service.reconstruct_proposal_state("missing") == {
        "id": "missing",
        "found": False,
    }


def test_proposal_reconstruction_api_endpoints(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    proposals = ProposalService(tmp_path / "proposals.db", events=events)
    reconstruct_routes.reconstruction_service = ReconstructionService(
        events=EventService(trace_store),
        proposals=proposals,
    )
    client = TestClient(app)

    created = proposals.create_proposal("API proposal", "Body")

    assert client.get("/reconstruct/proposals").json()[0]["id"] == created.id
    assert (
        client.get(f"/reconstruct/proposals/{created.id}").json()["id"]
        == created.id
    )
    comparison = client.get(
        f"/reconstruct/proposals/{created.id}/compare"
    ).json()
    assert comparison["consistent"] is True


def test_planner_recommendation_reconstruction_api_endpoints(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    reconstruct_routes.reconstruction_service = ReconstructionService(
        events=EventService(trace_store),
    )
    client = TestClient(app)

    events.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_CREATED,
        "Recommendation created",
        metadata={
            "recommendation_id": "recommendation-1",
            "task_id": "task-1",
            "session_id": "session-1",
            "objective": "Inspect README",
            "proposed_tool": {"name": "shell.read"},
            "rationale": "Selected first enabled tool: shell.read",
            "confidence": 0.75,
            "governance_status": "ok",
            "created_at": "2026-06-05T00:00:00+00:00",
        },
    )

    list_response = client.get("/reconstruct/planner-recommendations")
    filtered_response = client.get(
        "/reconstruct/planner-recommendations",
        params={"session_id": "session-1"},
    )
    lineage_response = client.get(
        "/reconstruct/planner-recommendations/recommendation-1"
    )
    consistency_response = client.get(
        "/reconstruct/planner-recommendations/consistency"
    )

    assert list_response.status_code == 200
    assert filtered_response.status_code == 200
    assert lineage_response.status_code == 200
    assert consistency_response.status_code == 200
    assert list_response.json()[0]["recommendation_id"] == "recommendation-1"
    assert filtered_response.json()[0]["session_id"] == "session-1"
    assert lineage_response.json()["objective"] == "Inspect README"
    assert consistency_response.json()["consistent"] is True
