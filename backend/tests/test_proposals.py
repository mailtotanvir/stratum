from fastapi.testclient import TestClient

from app.main import app
from app.routes import proposal as proposal_routes
from app.routes.stream import trace
from app.services.event_service import EventService, event_service
from app.services.proposal_service import ProposalService
from app.services.trace_service import TraceService


def test_create_proposal_persists(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")

    created = service.create_proposal(
        title="Add validation",
        body="Validate proposal inputs.",
        task_id="task-1",
    )
    reader = ProposalService(tmp_path / "proposals.db")

    persisted = reader.get_proposal(created.id)
    assert persisted.id == created.id
    assert persisted.title == "Add validation"
    assert persisted.body == "Validate proposal inputs."
    assert persisted.task_id == "task-1"
    assert persisted.source_type == "manual"
    assert persisted.source_id is None
    assert persisted.status == "proposed"
    assert persisted.resolved_at is None
    assert persisted.decision is None


def test_list_proposals(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")
    first = service.create_proposal("First", "Body")
    second = service.create_proposal("Second", "Body")

    assert [proposal.id for proposal in service.list_proposals()] == [
        second.id,
        first.id,
    ]


def test_list_proposals_filters_by_status(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")
    proposed = service.create_proposal("Proposed", "Body")
    approved = service.create_proposal("Approved", "Body")
    service.respond(approved.id, "approve")

    assert [proposal.id for proposal in service.list_proposals(status="proposed")] == [
        proposed.id,
    ]
    assert service.list_proposals(status="approved")[0].id == approved.id


def test_list_proposals_filters_by_task_id(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")
    first = service.create_proposal("First", "Body", task_id="task-1")
    service.create_proposal("Second", "Body", task_id="task-2")

    assert [proposal.id for proposal in service.list_proposals(task_id="task-1")] == [
        first.id,
    ]


def test_get_proposal_source_returns_lineage(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")
    manual = service.create_proposal("Manual", "Body")
    planner = service.create_proposal(
        "Planner",
        "Body",
        source_type="planner_recommendation",
        source_id="recommendation-1",
    )

    assert service.get_proposal_source(manual.id) == {
        "proposal_id": manual.id,
        "source_type": "manual",
        "source_id": None,
    }
    assert service.get_proposal_source(planner.id) == {
        "proposal_id": planner.id,
        "source_type": "planner_recommendation",
        "source_id": "recommendation-1",
        "recommendation_id": "recommendation-1",
    }


def test_approve_transition(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")
    created = service.create_proposal("Approve me", "Body")

    approved = service.respond(created.id, "approve")

    assert approved.status == "approved"
    assert approved.decision == "approve"
    assert approved.resolved_at is not None
    assert service.get_proposal(created.id).status == "approved"


def test_reject_transition(tmp_path) -> None:
    service = ProposalService(tmp_path / "proposals.db")
    created = service.create_proposal("Reject me", "Body")

    rejected = service.respond(created.id, "reject")

    assert rejected.status == "rejected"
    assert rejected.decision == "reject"
    assert rejected.resolved_at is not None
    assert service.get_proposal(created.id).status == "rejected"


def test_proposal_lifecycle_events_appear_in_trace(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    event_service.set_trace_store(trace_store)
    service = ProposalService(tmp_path / "proposals.db", events=event_service)

    created = service.create_proposal(
        "Trace proposal",
        "Body",
        task_id="task-1",
    )
    service.respond(created.id, "approve")

    persisted = trace()

    assert [event["type"] for event in persisted[-2:]] == [
        "proposal_generated",
        "proposal_resolved",
    ]
    assert [event["metadata"]["proposal_id"] for event in persisted[-2:]] == [
        created.id,
        created.id,
    ]
    assert persisted[-1]["metadata"]["decision"] == "approve"
    assert persisted[-1]["metadata"]["status"] == "approved"
    assert persisted[-2]["metadata"]["source_type"] == "manual"
    assert persisted[-2]["metadata"]["source_id"] is None
    assert persisted[-1]["metadata"]["source_type"] == "manual"
    assert persisted[-1]["metadata"]["source_id"] is None


def test_double_response_rejected(tmp_path) -> None:
    proposal_routes.proposal_service = ProposalService(tmp_path / "proposals.db")
    client = TestClient(app)
    created = client.post(
        "/proposals",
        json={"title": "Resolve once", "body": "Body"},
    ).json()

    first = client.post(
        f"/proposals/{created['id']}/respond",
        json={"decision": "approve"},
    )
    second = client.post(
        f"/proposals/{created['id']}/respond",
        json={"decision": "reject"},
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_unknown_proposal_returns_404(tmp_path) -> None:
    proposal_routes.proposal_service = ProposalService(tmp_path / "proposals.db")
    client = TestClient(app)

    get_response = client.get("/proposals/missing")
    respond_response = client.post(
        "/proposals/missing/respond",
        json={"decision": "approve"},
    )

    assert get_response.status_code == 404
    assert respond_response.status_code == 404


def test_proposal_api_create_get_list_and_filters(tmp_path) -> None:
    proposal_routes.proposal_service = ProposalService(tmp_path / "proposals.db")
    client = TestClient(app)

    first = client.post(
        "/proposals",
        json={"title": "First", "body": "Body", "task_id": "task-1"},
    ).json()
    second = client.post(
        "/proposals",
        json={"title": "Second", "body": "Body", "task_id": "task-2"},
    ).json()

    assert first["source_type"] == "manual"
    assert first["source_id"] is None
    assert second["source_type"] == "manual"
    assert second["source_id"] is None
    assert client.get(f"/proposals/{first['id']}").json() == first
    assert client.get("/proposals").json() == [second, first]
    assert client.get("/proposals", params={"status": "proposed"}).json() == [
        second,
        first,
    ]
    assert client.get("/proposals", params={"task_id": "task-1"}).json() == [first]


def test_proposal_trace_returns_only_events_for_requested_proposal() -> None:
    first = event_service.emit_event_sync(
        "proposal_generated",
        "First proposal",
        metadata={"proposal_id": "proposal-1"},
    )
    event_service.emit_event_sync(
        "proposal_generated",
        "Second proposal",
        metadata={"proposal_id": "proposal-2"},
    )
    resolved = event_service.emit_event_sync(
        "proposal_resolved",
        "First proposal resolved",
        metadata={"proposal_id": "proposal-1"},
    )
    client = TestClient(app)

    response = client.get("/proposals/proposal-1/trace")

    assert response.status_code == 200
    assert response.json() == [first.to_dict(), resolved.to_dict()]


def test_proposal_trace_type_filter_uses_proposal_id_and_type() -> None:
    event_service.emit_event_sync(
        "proposal_resolved",
        "Other proposal resolved",
        metadata={"proposal_id": "proposal-2"},
    )
    expected = event_service.emit_event_sync(
        "proposal_resolved",
        "Target proposal resolved",
        metadata={"proposal_id": "proposal-1"},
    )
    event_service.emit_event_sync(
        "proposal_generated",
        "Target proposal generated",
        metadata={"proposal_id": "proposal-1"},
    )
    client = TestClient(app)

    response = client.get(
        "/proposals/proposal-1/trace",
        params={"type": "proposal_resolved"},
    )

    assert response.status_code == 200
    assert response.json() == [expected.to_dict()]


def test_proposal_trace_limit_returns_recent_matches_in_chronological_order() -> None:
    event_service.emit_event_sync(
        "proposal_generated",
        "First proposal event",
        metadata={"proposal_id": "proposal-1"},
    )
    second = event_service.emit_event_sync(
        "proposal_resolved",
        "Second proposal event",
        metadata={"proposal_id": "proposal-1"},
    )
    third = event_service.emit_event_sync(
        "proposal_generated",
        "Third proposal event",
        metadata={"proposal_id": "proposal-1"},
    )
    event_service.emit_event_sync(
        "proposal_generated",
        "Other proposal event",
        metadata={"proposal_id": "proposal-2"},
    )
    client = TestClient(app)

    response = client.get("/proposals/proposal-1/trace", params={"limit": 2})

    assert response.status_code == 200
    assert response.json() == [second.to_dict(), third.to_dict()]


def test_proposal_trace_unknown_proposal_id_returns_empty_list() -> None:
    event_service.emit_event_sync(
        "proposal_generated",
        "Known proposal",
        metadata={"proposal_id": "proposal-1"},
    )
    client = TestClient(app)

    response = client.get("/proposals/unknown/trace")

    assert response.status_code == 200
    assert response.json() == []
