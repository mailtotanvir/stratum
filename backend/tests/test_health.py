import asyncio

import pytest

from app.main import app, health
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.routes.hitl import HumanResponse, demo_ask, demo_result, pending, respond
from app.routes.stream import demo_event, format_sse, trace
from app.services.event_service import EventService, event_service
from app.services.trace_service import TraceService


@pytest.fixture(autouse=True)
def use_temp_trace_store(tmp_path):
    event_service.set_trace_store(TraceService(tmp_path / "stratum.db"))


async def next_event(queue: asyncio.Queue[RuntimeEvent]) -> RuntimeEvent:
    return await asyncio.wait_for(queue.get(), timeout=1)


def test_health() -> None:
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert health() == {"status": "ok", "service": "stratum-backend"}


def test_hitl_demo_flow() -> None:
    async def run_flow() -> None:
        start_response = await demo_ask()

        assert start_response == {"status": "started"}
        assert await pending() == {"question": "What colour is the sky?"}

        async with event_service.subscribe(replay_existing=False) as queue:
            response = await respond(HumanResponse(text="blue"))
            await next_event(queue)
            completed = await next_event(queue)

        assert response == {"status": "ok"}
        assert completed.type == "demo_task_completed"
        assert await pending() is None

        result = await demo_result()
        assert result["pending"] is None
        assert result["running"] is False
        assert result["result"] == "You answered: blue"

    asyncio.run(run_flow())


def test_hitl_routes_emit_ordered_events_with_metadata() -> None:
    async def run_flow() -> None:
        async with event_service.subscribe(replay_existing=False) as queue:
            start_response = await demo_ask()
            requested = await next_event(queue)

            response = await respond(HumanResponse(text="blue"))
            responded = await next_event(queue)
            completed = await next_event(queue)

        assert start_response == {"status": "started"}
        assert response == {"status": "ok"}
        assert [requested.type, responded.type, completed.type] == [
            "ask_human_requested",
            "ask_human_responded",
            "demo_task_completed",
        ]
        assert requested.metadata == {"question": "What colour is the sky?"}
        assert responded.metadata == {"response": "blue"}
        assert completed.metadata == {
            "answer": "blue",
            "result": "You answered: blue",
        }
        assert requested.message == "What colour is the sky?"
        assert responded.message == "Human response submitted."
        assert completed.message == "Demo task completed."

    asyncio.run(run_flow())


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
