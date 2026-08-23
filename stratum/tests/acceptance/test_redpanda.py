"""Acceptance test: events cross a REAL Redpanda/Kafka broker and replay
reconstructs the same execution history.

Requires STRATUM_KAFKA_BROKERS (e.g. 127.0.0.1:9092 with the provided
docker-compose.redpanda.yml). Skips cleanly without it.
"""

from __future__ import annotations

import os

import pytest

from stratum.events import (
    APPROVAL_GRANTED,
    ARTIFACT_CREATED,
    PLAN_GENERATED,
    TASK_COMPLETED,
    TASK_CREATED,
    EventFactory,
)
from stratum.ids import execution_id, task_id

pytestmark = pytest.mark.acceptance_broker


def _brokers():
    brokers = os.environ.get("STRATUM_KAFKA_BROKERS")
    if not brokers:
        pytest.skip("STRATUM_KAFKA_BROKERS not set; broker acceptance not exercised")
    return [b.strip() for b in brokers.split(",") if b.strip()]


def test_events_roundtrip_through_real_broker(tmp_path):
    from stratum.redpanda import RedpandaEventPublisher, RedpandaEventReader

    brokers = _brokers()
    eid = execution_id()
    tid = task_id()
    factory = EventFactory(tid, eid)

    events = [
        factory.emit(TASK_CREATED, {"description": "broker acceptance", "repo_path": "/tmp/x"}),
        factory.emit(PLAN_GENERATED, {"plan": {"id": "p1", "rationale": "r",
                                               "steps": [{"index": 1}]}}),
        factory.emit(APPROVAL_GRANTED, {"plan_id": "p1", "decider": "harness"}),
        factory.emit(ARTIFACT_CREATED, {"path": "hello.py", "bytes": 42, "diff": "-a\n+b"}),
        factory.emit(TASK_COMPLETED, {"steps_total": 1, "steps_ok": 1}),
    ]

    import asyncio

    async def produce():
        publisher = RedpandaEventPublisher(brokers=brokers)
        try:
            for event in events:
                await publisher.publish(event)
        finally:
            await publisher.close()

    asyncio.run(produce())

    reader = RedpandaEventReader(brokers=brokers)
    received = reader.read_execution(eid)

    # Ordering preserved (single partition per execution key).
    assert [e.sequence for e in received] == [1, 2, 3, 4, 5]
    assert all(e.execution_id == eid for e in received)

    # Replay over broker-read events yields identical reconstructed history.
    from stratum.replay import fold

    replayed = fold(received)
    assert replayed.status == "COMPLETED"
    assert replayed.approval == "granted"
    assert replayed.artifacts[0]["path"] == "hello.py"
