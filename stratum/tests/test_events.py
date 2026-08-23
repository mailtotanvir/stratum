from stratum.events import (
    APPROVAL_GRANTED,
    TASK_CREATED,
    EVENT_TYPES,
    EventFactory,
    RuntimeEvent,
    sort_events,
)
from stratum.ids import execution_id, new_id, task_id


def test_ids_are_prefixed_and_sortable():
    a = new_id("tsk")
    b = new_id("tsk")
    assert a.startswith("tsk_") and b.startswith("tsk_")
    assert a != b


def test_task_and_execution_ids():
    assert task_id().startswith("tsk_")
    assert execution_id().startswith("exe_")


def test_event_factory_assigns_monotonic_sequences():
    factory = EventFactory(task_id(), execution_id())
    e1 = factory.emit(TASK_CREATED, {"description": "t"})
    e2 = factory.emit(APPROVAL_GRANTED, {"plan_id": "p"})
    assert e2.sequence == e1.sequence + 1
    # Causation chain: each event cites its predecessor.
    assert e2.causation_id == e1.event_id
    assert e1.correlation_id == e2.correlation_id


def test_event_factory_rejects_unknown_types():
    factory = EventFactory(task_id(), execution_id())
    try:
        factory.emit("not.an.event", {})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_event_json_roundtrip():
    factory = EventFactory(task_id(), execution_id())
    event = factory.emit(TASK_CREATED, {"description": "demo"})
    restored = RuntimeEvent.from_json(event.to_json())
    assert restored == event
    assert restored.payload["description"] == "demo"


def test_sort_orders_by_execution_then_sequence():
    f1 = EventFactory("t1", "e1")
    f2 = EventFactory("t2", "e2")
    a, b = f1.emit(TASK_CREATED, {}), f1.emit(APPROVAL_GRANTED, {})
    c = f2.emit(TASK_CREATED, {})
    ordered = sort_events([c, b, a])
    assert [(e.execution_id, e.sequence) for e in ordered] == [
        ("e1", 1), ("e1", 2), ("e2", 1),
    ]


def test_vocabulary_is_frozen_v1():
    assert len(EVENT_TYPES) == 17
