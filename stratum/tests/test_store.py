from __future__ import annotations

from pathlib import Path

from stratum.events import (
    APPROVAL_GRANTED,
    TASK_CREATED,
    EventFactory,
    RuntimeEvent,
)
from stratum.ids import execution_id, task_id
from stratum.store import SqliteEventStore


def _event(seq: int, eid: str, tid: str) -> RuntimeEvent:
    f = EventFactory(tid, eid)
    for _ in range(seq - 1):
        f.emit(TASK_CREATED, {"n": seq})
    return f.emit(TASK_CREATED, {"n": seq})


def test_event_roundtrip(tmp_path: Path):
    store = SqliteEventStore(tmp_path / "t.db")
    e1 = _event(1, "exe_a", "tsk_1")
    e2 = _event(2, "exe_a", "tsk_1")
    store.append(e1)
    store.append(e2)

    events = store.read_execution("exe_a")
    assert [e.event_id for e in events] == [e1.event_id, e2.event_id]
    assert events[1].sequence == 2
    assert events[0].payload["n"] == 1


def test_append_is_idempotent(tmp_path: Path):
    store = SqliteEventStore(tmp_path / "t.db")
    event = _event(1, "exe_a", "tsk_1")
    store.append(event)
    store.append(event)  # replay/duplicate delivery must not duplicate rows
    assert len(store.read_execution("exe_a")) == 1


def test_read_all_orders_by_execution_then_sequence(tmp_path: Path):
    store = SqliteEventStore(tmp_path / "t.db")
    b2 = _event(2, "exe_b", "tsk_b")
    a1 = _event(1, "exe_a", "tsk_a")
    a2 = _event(2, "exe_a", "tsk_a")
    b1 = _event(1, "exe_b", "tsk_b")
    for e in (b2, a1, a2, b1):
        store.append(e)
    got = [(e.execution_id, e.sequence) for e in store.read_all()]
    assert got == [("exe_a", 1), ("exe_a", 2), ("exe_b", 1), ("exe_b", 2)]


def test_execution_upsert_and_status_flow(tmp_path: Path):
    from stratum.planning import parse_plan

    store = SqliteEventStore(tmp_path / "t.db")

    plan = parse_plan(
        '{"rationale":"r","steps":[{"description":"x","action_type":"read_file",'
        '"path":"a.py"}]}',
        task_id="tsk_1",
    )
    store.upsert_execution(
        execution_id="exe_a", task_id="tsk_1", repo_path="/repo",
        task_description="do the thing", status="APPROVAL_REQUIRED",
        created_at="2026-01-01T00:00:00Z", plan=plan, correlation_id="evt_c",
        last_event_sequence=4,
    )
    record = store.get_execution("exe_a")
    assert record.status == "APPROVAL_REQUIRED"
    assert record.plan is not None and record.plan.id == plan.id
    assert record.correlation_id == "evt_c"
    assert record.last_event_sequence >= 4

    store.upsert_execution(
        execution_id="exe_a", task_id="tsk_1", repo_path="/repo",
        task_description="do the thing", status="COMPLETED",
        created_at="2026-01-01T00:00:00Z", decider="web-operator",
    )
    record = store.get_execution("exe_a")
    assert record.status == "COMPLETED"
    assert record.decider == "web-operator"
    # Plan and sequence watermark survive partial updates.
    assert record.plan is not None
    assert record.last_event_sequence >= 4

    pendings = store.pending_executions()
    assert pendings == []


def test_pending_executions_lists_awaiting_approval(tmp_path: Path):
    store = SqliteEventStore(tmp_path / "t.db")
    store.upsert_execution(
        execution_id="exe_p", task_id="tsk_p", repo_path="/repo",
        task_description="pending one", status="APPROVAL_REQUIRED",
        created_at="2026-01-02T00:00:00Z",
    )
    store.upsert_execution(
        execution_id="exe_d", task_id="tsk_d", repo_path="/repo",
        task_description="done one", status="COMPLETED",
        created_at="2026-01-01T00:00:00Z",
    )
    pendings = store.pending_executions()
    assert [r.execution_id for r in pendings] == ["exe_p"]

    listed = store.list_executions()
    assert {r.execution_id for r in listed} == {"exe_p", "exe_d"}


def test_plan_json_roundtrip_preserves_content(tmp_path: Path):
    from stratum.planning import parse_plan

    plan = parse_plan(
        '{"rationale":"r","steps":['
        '{"description":"w","action_type":"write_file","path":"hello.py",'
        '"content_summary":"s","content":"x = 1\\n"}]}',
        task_id="tsk_1",
    )
    restored = type(plan).from_json(plan.to_json())
    assert restored == plan
