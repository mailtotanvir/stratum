"""The authoritative runtime event contract.

Every meaningful execution transition produces a RuntimeEvent. Events are
append-only facts. Projections, replay, and the live trace are all derived
from this stream — never the other way around.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


# ---------------------------------------------------------------------------
# Event types (v1 vocabulary)
# ---------------------------------------------------------------------------

TASK_CREATED = "task.created"
TASK_PLANNING_STARTED = "task.planning_started"
AI_REQUESTED = "ai.requested"
AI_RESPONDED = "ai.responded"
PLAN_GENERATED = "plan.generated"
APPROVAL_REQUESTED = "approval.requested"
APPROVAL_GRANTED = "approval.granted"
APPROVAL_REJECTED = "approval.rejected"
EXECUTION_STARTED = "execution.started"
TOOL_STARTED = "tool.started"
TOOL_COMPLETED = "tool.completed"
TOOL_FAILED = "tool.failed"
ARTIFACT_CREATED = "artifact.created"
OBSERVATION_RECORDED = "observation.recorded"
TASK_COMPLETED = "task.completed"
TASK_FAILED = "task.failed"
TASK_CANCELLED = "task.cancelled"

EVENT_TYPES: frozenset[str] = frozenset(
    {
        TASK_CREATED,
        TASK_PLANNING_STARTED,
        AI_REQUESTED,
        AI_RESPONDED,
        PLAN_GENERATED,
        APPROVAL_REQUESTED,
        APPROVAL_GRANTED,
        APPROVAL_REJECTED,
        EXECUTION_STARTED,
        TOOL_STARTED,
        TOOL_COMPLETED,
        TOOL_FAILED,
        ARTIFACT_CREATED,
        OBSERVATION_RECORDED,
        TASK_COMPLETED,
        TASK_FAILED,
        TASK_CANCELLED,
    }
)

EVENT_SCHEMA_VERSION = 1
DEFAULT_TOPIC = "stratum.runtime.events.v1"
PRODUCER = "stratum-runtime"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class RuntimeEvent:
    """An immutable fact about something that actually happened."""

    event_id: str
    event_type: str
    event_version: int
    task_id: str
    execution_id: str
    timestamp: str
    sequence: int
    producer: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(
            event_id=data["event_id"],
            event_type=data["event_type"],
            event_version=int(data.get("event_version", EVENT_SCHEMA_VERSION)),
            task_id=data["task_id"],
            execution_id=data["execution_id"],
            timestamp=data["timestamp"],
            sequence=int(data["sequence"]),
            producer=data.get("producer", PRODUCER),
            payload=dict(data.get("payload") or {}),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
        )

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("utf-8")

    @staticmethod
    def from_json(raw: bytes | str) -> RuntimeEvent:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return RuntimeEvent.from_dict(json.loads(raw))


class EventFactory:
    """Assigns monotonic per-execution sequences and causal linkage.

    Supports resumption: pass ``start_sequence`` and ``correlation_id`` to
    continue an execution's event chain after a process restart.
    """

    def __init__(
        self,
        task_id: str,
        execution_id: str,
        *,
        start_sequence: int = 0,
        correlation_id: str | None = None,
    ) -> None:
        from .ids import event_id

        self.task_id = task_id
        self.execution_id = execution_id
        self._sequence = start_sequence
        self._last_event_id: str | None = None
        self._correlation_id = correlation_id or event_id()

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        causation_id: str | None = None,
    ) -> RuntimeEvent:
        from .ids import event_id

        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type!r}")
        self._sequence += 1
        eid = event_id()
        event = RuntimeEvent(
            event_id=eid,
            event_type=event_type,
            event_version=EVENT_SCHEMA_VERSION,
            task_id=self.task_id,
            execution_id=self.execution_id,
            timestamp=utc_now_iso(),
            sequence=self._sequence,
            producer=PRODUCER,
            payload=payload,
            correlation_id=self._correlation_id,
            causation_id=causation_id or self._last_event_id,
        )
        self._last_event_id = eid
        return event


def sort_events(events: list[RuntimeEvent]) -> list[RuntimeEvent]:
    """Canonical ordering for replay: execution, then sequence."""
    return sorted(events, key=lambda e: (e.execution_id, e.sequence))
