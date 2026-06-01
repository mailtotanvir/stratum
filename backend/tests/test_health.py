import asyncio

from app.main import app, health
from app.routes.hitl import HumanResponse, demo_ask, demo_result, pending, respond


def test_health() -> None:
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert health() == {"status": "ok", "service": "stratum-backend"}


def test_hitl_demo_flow() -> None:
    async def run_flow() -> None:
        start_response = await demo_ask()

        assert start_response == {"status": "started"}
        assert await pending() == {"question": "What colour is the sky?"}

        response = await respond(HumanResponse(text="blue"))
        await asyncio.sleep(0)

        assert response == {"status": "ok"}
        assert await pending() is None

        result = await demo_result()
        assert result["pending"] is None
        assert result["running"] is False
        assert result["result"] == "You answered: blue"

    asyncio.run(run_flow())
