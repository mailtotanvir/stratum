"""Local durable event journal.

An append-only NDJSON file acting as the local event index/cache alongside
the broker. It is NOT a competing source of truth: when a broker is
configured, Redpanda is authoritative and this journal is a convenience
projection for offline replay. When no broker is configured (pure local
mode), it is the persistence boundary of last resort.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .events import RuntimeEvent
from .publisher import EventPublisher


class FileEventJournal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- write side ---------------------------------------------------------

    def append(self, event: RuntimeEvent) -> None:
        line = json.dumps(event.to_dict(), separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # -- read side ----------------------------------------------------------

    def read_all(self) -> list[RuntimeEvent]:
        if not self.path.exists():
            return []
        events: list[RuntimeEvent] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(RuntimeEvent.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    # A torn final line must not poison the whole journal.
                    continue
        return events

    def read_execution(self, execution_id: str) -> list[RuntimeEvent]:
        return [e for e in self.read_all() if e.execution_id == execution_id]


class JournalPublisher(EventPublisher):
    """Publisher adapter over the file journal."""

    def __init__(self, journal: FileEventJournal) -> None:
        self.journal = journal

    async def publish(self, event: RuntimeEvent) -> None:
        await asyncio.to_thread(self.journal.append, event)

    async def close(self) -> None:
        return None
