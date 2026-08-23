"""Engine persistence: durable state, restart recovery, cross-process
approval. The store is the local projection; events remain authoritative.
"""

from __future__ import annotations

import json
import sys

from stratum.adapters.scripted import ScriptedAdapter, scripted_json_response
from stratum.approval import PreDecidedApprovalPolicy
from stratum.engine import ExecutionStatus, StratumRuntime
from stratum.publisher import InMemoryEventPublisher
from stratum.store import SqliteEventStore

NEW_CONTENT = 'def greeting():\n    return "Hello Stratum"\n'


def plan_json() -> str:
    return json.dumps({
        "rationale": "r",
        "steps": [
            {"description": "read", "action_type": "read_file", "path": "hello.py"},
            {"description": "write", "action_type": "write_file",
             "path": "hello.py", "content": NEW_CONTENT},
            {"description": "update test", "action_type": "write_file",
             "path": "test_hello.py",
             "content": 'from hello import greeting\n\n\ndef test_greeting():\n'
                        '    assert greeting() == "Hello Stratum"\n'},
            {"description": "test", "action_type": "run_command",
             "command": f"{sys.executable} -m pytest -q"},
        ],
    })


def make_runtime(store, decision="granted") -> StratumRuntime:
    return StratumRuntime(
        adapter=ScriptedAdapter([scripted_json_response(plan_json())]),
        model="scripted-model",
        publisher=InMemoryEventPublisher(),
        approval_policy=PreDecidedApprovalPolicy(decision),
        store=store,
    )


def _no_ai(request):
    """The resume/approve/execute path must never call the provider."""
    raise AssertionError("unexpected AI call after restart")


def restarted_runtime(store, decision="granted") -> StratumRuntime:
    return StratumRuntime(
        adapter=ScriptedAdapter(responder=_no_ai),
        model="scripted-model",
        publisher=InMemoryEventPublisher(),
        approval_policy=PreDecidedApprovalPolicy(decision),
        store=store,
    )


async def test_pending_execution_survives_restart_and_completes(git_repo, tmp_path):
    # --- process 1: plan only, then die before any approval ---------------
    db = tmp_path / "stratum.db"
    runtime1 = make_runtime(SqliteEventStore(db))
    snapshot = await runtime1.start_planning(
        repo_path=git_repo, task_description='change greeting to "Hello Stratum"')
    assert snapshot.status.value == "APPROVAL_REQUIRED"
    eid = snapshot.execution_id
    del runtime1  # process dies; nothing in memory anymore

    # --- process 2: fresh engine over the same database --------------------
    runtime2 = restarted_runtime(SqliteEventStore(db))
    resumed = await runtime2.resume_pending()
    assert [s.execution_id for s in resumed] == [eid]
    assert resumed[0].plan is not None and len(resumed[0].plan.steps) == 4

    result = await runtime2.decide_and_execute(eid)

    assert result.status is ExecutionStatus.COMPLETED
    assert (git_repo / "hello.py").read_text() == NEW_CONTENT


async def test_resumed_events_continue_sequence_and_correlation(git_repo, tmp_path):
    db = tmp_path / "stratum.db"
    r1 = make_runtime(SqliteEventStore(db))
    snap = await r1.start_planning(repo_path=git_repo, task_description="t")
    eid = snap.execution_id

    store2 = SqliteEventStore(db)
    r2 = restarted_runtime(store2)
    resumed = await r2.resume_pending()
    assert [x.execution_id for x in resumed] == [eid]
    bus2_events = []
    r2._publisher = _Capture(bus2_events)
    await r2.decide_and_execute(eid)

    all_events = store2.read_execution(eid)
    sequences = [e.sequence for e in all_events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)      # no collisions across restart
    correlations = {e.correlation_id for e in all_events}
    assert len(correlations) == 1                     # one lineage


class _Capture:
    def __init__(self, sink):
        self.sink = sink

    async def publish(self, event):
        self.sink.append(event)

    async def close(self):
        pass


async def test_rejection_is_persisted(git_repo, tmp_path):
    db = tmp_path / "stratum.db"
    r1 = make_runtime(SqliteEventStore(db), decision="rejected")
    snap = await r1.start_planning(repo_path=git_repo, task_description="t")
    await r1.decide_and_execute(snap.execution_id)

    record = SqliteEventStore(db).get_execution(snap.execution_id)
    assert record.status == "REJECTED"
    assert record.decider == "pre-decided"
    assert SqliteEventStore(db).pending_executions() == []


async def test_failure_state_is_persisted(git_repo, tmp_path):
    failing = json.dumps({
        "rationale": "r",
        "steps": [{"description": "x", "action_type": "run_command",
                   "command": "false"}],
    })
    db = tmp_path / "stratum.db"
    runtime = StratumRuntime(
        adapter=ScriptedAdapter([scripted_json_response(failing)]),
        model="m", publisher=InMemoryEventPublisher(),
        approval_policy=PreDecidedApprovalPolicy("granted"),
        store=SqliteEventStore(db),
    )
    snap = await runtime.start_planning(repo_path=git_repo, task_description="t")
    await runtime.decide_and_execute(snap.execution_id)

    record = SqliteEventStore(db).get_execution(snap.execution_id)
    assert record.status == "FAILED"
    assert "verification failed" in record.error


async def test_events_are_indexed_as_emitted(git_repo, tmp_path):
    db = tmp_path / "stratum.db"
    runtime = make_runtime(SqliteEventStore(db))
    snap = await runtime.start_planning(repo_path=git_repo, task_description="t")
    result = await runtime.decide_and_execute(snap.execution_id)

    indexed = SqliteEventStore(db).read_execution(result.execution_id)
    # 8 lifecycle events + 3/tool-step x2 (read, run) + 4/write-step x2
    # (started/completed/artifact/observed) + task.completed = 23
    assert len(indexed) == 23
    assert indexed[-1].event_type == "task.completed"
