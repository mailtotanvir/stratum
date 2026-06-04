import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.routes.stream import demo_event, format_sse, trace
from app.services.event_service import EventService, event_service
from app.services.trace_service import TraceService


def test_event_service_subscriber_receives_events(tmp_path) -> None:
    async def run_flow() -> None:
        service = EventService(TraceService(tmp_path / "events.db"))

        async with service.subscribe(replay_existing=True) as queue:
            event = await service.emit_event(
                event_type=EventType.TASK_STARTED,
                severity="info",
                message="Test event",
                metadata={"source": "pytest"},
            )

            received = await asyncio.wait_for(queue.get(), timeout=1)

        assert received == event
        assert event.id == 1
        assert event.type == EventType.TASK_STARTED
        assert event.severity == Severity.INFO
        assert event.message == "Test event"
        assert event.metadata == {"source": "pytest"}

    asyncio.run(run_flow())


def test_emitted_events_are_persisted_in_order(tmp_path) -> None:
    async def run_flow() -> None:
        store = TraceService(tmp_path / "events.db")
        service = EventService(store)

        first = await service.emit_event(
            event_type=EventType.TASK_STARTED,
            severity=Severity.INFO,
            message="Started",
            metadata={"step": 1},
        )
        second = await service.emit_event(
            event_type=EventType.TASK_COMPLETED,
            severity=Severity.INFO,
            message="Completed",
            metadata={"step": 2},
        )

        persisted = store.list_events()

        assert persisted == [first, second]
        assert [event.id for event in persisted] == [1, 2]
        assert [event.message for event in persisted] == ["Started", "Completed"]
        assert [event.metadata for event in persisted] == [{"step": 1}, {"step": 2}]

    asyncio.run(run_flow())


def test_stream_routes_and_sse_format() -> None:
    paths = {route.path for route in app.routes}
    event = RuntimeEvent(
        id=7,
        ts="2026-06-01T00:00:00+00:00",
        type=EventType.TASK_STARTED,
        severity=Severity.INFO,
        message="Demo runtime event",
        metadata={"ok": True},
    )

    assert "/stream" in paths
    assert "/demo/event" in paths
    assert format_sse(event) == (
        'id: 7\nevent: task_started\ndata: {"id":7,'
        '"ts":"2026-06-01T00:00:00+00:00","type":"task_started",'
        '"severity":"info","message":"Demo runtime event",'
        '"metadata":{"ok":true}}\n\n'
    )


def test_demo_event_route_emits_event() -> None:
    async def run_flow() -> None:
        response = await demo_event()

        assert response["type"] == "task_started"
        assert response["severity"] == "info"
        assert response["message"] == "Demo runtime event"
        assert response["metadata"] == {}

    asyncio.run(run_flow())


def test_trace_route_returns_persisted_events_in_order() -> None:
    async def run_flow() -> None:
        first = await demo_event()
        second = await demo_event()

        persisted = trace()

        assert persisted[-2:] == [first, second]

    asyncio.run(run_flow())


def test_trace_without_filters_preserves_existing_behavior() -> None:
    async def run_flow() -> None:
        first = await demo_event()
        second = await demo_event()
        client = TestClient(app)

        assert client.get("/trace").json()[-2:] == [first, second]

    asyncio.run(run_flow())


def test_trace_filters_by_type() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(EventType.TASK_CREATED, "Created")
        running = await event_service.emit_event(EventType.TASK_RUNNING, "Running")
        await event_service.emit_event(EventType.TASK_COMPLETED, "Completed")
        client = TestClient(app)

        response = client.get("/trace", params={"type": "task_running"})

        assert response.status_code == 200
        assert response.json() == [running.to_dict()]

    asyncio.run(run_flow())


def test_trace_filters_by_task_id() -> None:
    async def run_flow() -> None:
        first = await event_service.emit_event(
            EventType.TASK_CREATED,
            "First",
            metadata={"task_id": "task-1"},
        )
        await event_service.emit_event(
            EventType.TASK_CREATED,
            "Second",
            metadata={"task_id": "task-2"},
        )
        completed = await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "First completed",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get("/trace", params={"task_id": "task-1"})

        assert response.status_code == 200
        assert response.json() == [first.to_dict(), completed.to_dict()]

    asyncio.run(run_flow())


def test_trace_filters_by_type_and_task_id() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "Other completed",
            metadata={"task_id": "task-2"},
        )
        expected = await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "Target completed",
            metadata={"task_id": "task-1"},
        )
        await event_service.emit_event(
            EventType.TASK_RUNNING,
            "Target running",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get(
            "/trace",
            params={"type": "task_completed", "task_id": "task-1"},
        )

        assert response.status_code == 200
        assert response.json() == [expected.to_dict()]

    asyncio.run(run_flow())


def test_trace_filters_by_proposal_id() -> None:
    async def run_flow() -> None:
        first = await event_service.emit_event(
            EventType.PROPOSAL_GENERATED,
            "First proposal",
            metadata={"proposal_id": "proposal-1"},
        )
        await event_service.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Second proposal",
            metadata={"proposal_id": "proposal-2"},
        )
        resolved = await event_service.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "First proposal resolved",
            metadata={"proposal_id": "proposal-1"},
        )
        client = TestClient(app)

        response = client.get("/trace", params={"proposal_id": "proposal-1"})

        assert response.status_code == 200
        assert response.json() == [first.to_dict(), resolved.to_dict()]

    asyncio.run(run_flow())


def test_trace_filters_by_type_and_proposal_id() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Other proposal resolved",
            metadata={"proposal_id": "proposal-2"},
        )
        expected = await event_service.emit_event(
            EventType.PROPOSAL_RESOLVED,
            "Target proposal resolved",
            metadata={"proposal_id": "proposal-1"},
        )
        await event_service.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Target proposal generated",
            metadata={"proposal_id": "proposal-1"},
        )
        client = TestClient(app)

        response = client.get(
            "/trace",
            params={"type": "proposal_resolved", "proposal_id": "proposal-1"},
        )

        assert response.status_code == 200
        assert response.json() == [expected.to_dict()]

    asyncio.run(run_flow())


def test_trace_filters_by_task_id_and_proposal_id() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Wrong task",
            metadata={"task_id": "task-2", "proposal_id": "proposal-1"},
        )
        await event_service.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Wrong proposal",
            metadata={"task_id": "task-1", "proposal_id": "proposal-2"},
        )
        expected = await event_service.emit_event(
            EventType.PROPOSAL_GENERATED,
            "Target",
            metadata={"task_id": "task-1", "proposal_id": "proposal-1"},
        )
        client = TestClient(app)

        response = client.get(
            "/trace",
            params={"task_id": "task-1", "proposal_id": "proposal-1"},
        )

        assert response.status_code == 200
        assert response.json() == [expected.to_dict()]

    asyncio.run(run_flow())


def test_trace_limit_returns_most_recent_matches_in_chronological_order() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.TASK_RUNNING,
            "First running",
            metadata={"task_id": "task-1"},
        )
        second = await event_service.emit_event(
            EventType.TASK_RUNNING,
            "Second running",
            metadata={"task_id": "task-1"},
        )
        third = await event_service.emit_event(
            EventType.TASK_RUNNING,
            "Third running",
            metadata={"task_id": "task-1"},
        )
        await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "Completed",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get(
            "/trace",
            params={"type": "task_running", "task_id": "task-1", "limit": 2},
        )

        assert response.status_code == 200
        assert response.json() == [second.to_dict(), third.to_dict()]

    asyncio.run(run_flow())
