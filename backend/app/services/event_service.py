import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.services.trace_service import TraceService, trace_service


class EventService:
    def __init__(self, trace_store: TraceService | None = None) -> None:
        self._lock = asyncio.Lock()
        self._events: list[RuntimeEvent] = []
        self._subscribers: set[asyncio.Queue[RuntimeEvent]] = set()
        self._next_id = 1
        self._trace_store = trace_store or trace_service

    def set_trace_store(self, trace_store: TraceService) -> None:
        self._trace_store = trace_store

    async def list_events(self) -> list[RuntimeEvent]:
        async with self._lock:
            return list(self._events)

    def list_persisted_events(
        self,
        event_type: str | None = None,
        task_id: str | None = None,
        proposal_id: str | None = None,
        limit: int | None = None,
    ) -> list[RuntimeEvent]:
        return self._trace_store.list_events(
            event_type=event_type,
            task_id=task_id,
            proposal_id=proposal_id,
            limit=limit,
        )

    async def emit_event(
        self,
        event_type: EventType | str,
        message: str,
        severity: Severity | str = Severity.INFO,
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
            self._trace_store.append_event(event)
            self._events.append(event)

            for subscriber in self._subscribers:
                subscriber.put_nowait(event)

            return event

    def emit_event_sync(
        self,
        event_type: EventType | str,
        message: str,
        severity: Severity | str = Severity.INFO,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        return asyncio.run(
            self.emit_event(
                event_type=event_type,
                severity=severity,
                message=message,
                metadata=metadata,
            )
        )

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
    event_type: EventType | str,
    message: str,
    severity: Severity | str = Severity.INFO,
    metadata: dict[str, Any] | None = None,
) -> RuntimeEvent:
    return await event_service.emit_event(
        event_type=event_type,
        severity=severity,
        message=message,
        metadata=metadata,
    )


def emit_event_sync(
    event_type: EventType | str,
    message: str,
    severity: Severity | str = Severity.INFO,
    metadata: dict[str, Any] | None = None,
) -> RuntimeEvent:
    return event_service.emit_event_sync(
        event_type=event_type,
        severity=severity,
        message=message,
        metadata=metadata,
    )
