"""Event publishing seam.

The runtime emits events through this boundary and nowhere else. Concrete
publishers: InMemory (unit tests / ephemeral), FileJournal (durable local
index), Redpanda (authoritative Kafka-compatible stream).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from .events import RuntimeEvent


class EventPublisher(Protocol):
    async def publish(self, event: RuntimeEvent) -> None: ...

    async def close(self) -> None: ...


class InMemoryEventPublisher:
    """Retains events in process. For tests and ephemeral runs only.

    This is NOT an event system of record and must never be treated as one.
    """

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    async def publish(self, event: RuntimeEvent) -> None:
        self.events.append(event)

    async def close(self) -> None:
        return None

    def by_execution(self, execution_id: str) -> list[RuntimeEvent]:
        return [e for e in self.events if e.execution_id == execution_id]


class CompositeEventPublisher:
    """Fans out each event to multiple publishers (e.g. journal + broker)."""

    def __init__(self, *publishers: EventPublisher) -> None:
        if not publishers:
            raise ValueError("CompositeEventPublisher requires at least one publisher")
        self._publishers = publishers

    async def publish(self, event: RuntimeEvent) -> None:
        # Publish in order so the durable local index lands before we
        # consider the event emitted even if a broker is slow.
        errors: list[Exception] = []
        for publisher in self._publishers:
            try:
                await publisher.publish(event)
            except Exception as exc:  # noqa: BLE001 - broker outages must not kill execution mid-step
                errors.append(exc)
        if len(errors) == len(self._publishers):
            raise errors[0]

    async def close(self) -> None:
        for publisher in self._publishers:
            await publisher.close()


def run_publisher_sync(publisher: EventPublisher, event: RuntimeEvent) -> None:
    """Bridge for synchronous callers (CLI replay/consume helpers)."""
    asyncio.run(publisher.publish(event))
