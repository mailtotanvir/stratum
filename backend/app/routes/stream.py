import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.services.event_service import emit_event, event_service

router = APIRouter()


class DemoEventRequest(BaseModel):
    type: EventType = EventType.TASK_STARTED
    severity: Severity = Severity.INFO
    message: str = "Demo runtime event"
    metadata: dict[str, Any] = Field(default_factory=dict)


def format_sse(event: RuntimeEvent) -> str:
    data = json.dumps(event.to_dict(), separators=(",", ":"))
    return f"id: {event.id}\nevent: {event.type}\ndata: {data}\n\n"


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    async def event_generator():
        async with event_service.subscribe(replay_existing=True) as queue:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield format_sse(event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/demo/event")
async def demo_event(request: DemoEventRequest | None = None) -> dict[str, Any]:
    event_request = request or DemoEventRequest()
    event = await emit_event(
        event_type=event_request.type,
        severity=event_request.severity,
        message=event_request.message,
        metadata=event_request.metadata,
    )
    return event.to_dict()


@router.get("/trace")
def trace() -> list[dict[str, Any]]:
    return [event.to_dict() for event in event_service.list_persisted_events()]
