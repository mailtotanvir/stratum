import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class RuntimeEvent:
    id: int
    ts: str
    type: str
    severity: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "metadata": self.metadata,
        }


class EventService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._events: list[RuntimeEvent] = []
        self._subscribers: set[asyncio.Queue[RuntimeEvent]] = set()
        self._next_id = 1

    async def list_events(self) -> list[RuntimeEvent]:
        async with self._lock:
            return list(self._events)

    async def emit_event(
        self,
        event_type: str,
        message: str,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        async with self._lock:
            event = RuntimeEvent(
                id=self._next_id,
                ts=datetime.now(UTC).isoformat(),
                type=event_type,
                severity=severity,
                message=message,
                metadata=metadata or {},
            )
            self._next_id += 1
            self._events.append(event)

            for subscriber in self._subscribers:
                subscriber.put_nowait(event)

            return event

    @asynccontextmanager
    async def subscribe(
        self, replay_existing: bool = True
    ) -> AsyncIterator[asyncio.Queue[RuntimeEvent]]:
        queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue()

        async with self._lock:
            self._subscribers.add(queue)
            if replay_existing:
                for event in self._events:
                    queue.put_nowait(event)

        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)


event_service = EventService()


async def emit_event(
    event_type: str,
    message: str,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
) -> RuntimeEvent:
    return await event_service.emit_event(
        event_type=event_type,
        severity=severity,
        message=message,
        metadata=metadata,
    )

