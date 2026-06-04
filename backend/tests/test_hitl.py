import asyncio

from app.models.runtime_event import RuntimeEvent
from app.routes.hitl import HumanResponse, demo_ask, demo_result, pending, respond
from app.services.event_service import event_service


async def next_event(queue: asyncio.Queue[RuntimeEvent]) -> RuntimeEvent:
    return await asyncio.wait_for(queue.get(), timeout=1)


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

