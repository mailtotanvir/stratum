"""Vertical integration tests over the real runtime spine.

Real repository fixture, real tools, real filesystem effects, real
subprocess verification, real event journal + replay. The provider is
scripted here for speed/determinism — this file proves WIRING, not product
acceptance. Acceptance lives in tests/acceptance/ and requires real
provider/broker infrastructure.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from stratum.adapters.scripted import ScriptedAdapter, scripted_json_response
from stratum.approval import PreDecidedApprovalPolicy
from stratum.engine import ExecutionStatus, StratumRuntime
from stratum.events import (
    AI_REQUESTED,
    ARTIFACT_CREATED,
    EXECUTION_STARTED,
    PLAN_GENERATED,
    TASK_COMPLETED,
    TOOL_COMPLETED,
    TOOL_STARTED,
)
from stratum.journal import FileEventJournal, JournalPublisher
from stratum.publisher import CompositeEventPublisher, InMemoryEventPublisher

NEW_CONTENT = 'def greeting():\n    return "Hello Stratum"\n'


def plan_json(content: str | None = None) -> str:
    step_write = {
        "description": "Change greeting to Hello Stratum",
        "action_type": "write_file",
        "path": "hello.py",
        "content_summary": 'return "Hello Stratum"',
    }
    if content is not None:
        step_write["content"] = content
    return json.dumps({
        "rationale": "Update greeting string and verify via tests",
        "steps": [
            {"description": "Read hello.py", "action_type": "read_file",
             "path": "hello.py", "risk": "low", "requires_approval": False},
            step_write,
            {"description": "Update the test expectation",
             "action_type": "write_file", "path": "test_hello.py",
             "content_summary": 'assert greeting() == "Hello Stratum"',
             "content": 'from hello import greeting\n\n\ndef test_greeting():\n'
                        '    assert greeting() == "Hello Stratum"\n'},
            {"description": "Run tests", "action_type": "run_command",
             "command": f"{sys.executable} -m pytest -q", "risk": "medium"},
        ],
    })


def make_runtime(git_repo, data_dir, responses, decision="granted"):
    bus = InMemoryEventPublisher()
    journal = FileEventJournal(data_dir / "events.ndjson")
    runtime = StratumRuntime(
        adapter=ScriptedAdapter([scripted_json_response(r) for r in responses]),
        model="scripted-model",
        publisher=CompositeEventPublisher(bus, JournalPublisher(journal)),
        approval_policy=PreDecidedApprovalPolicy(decision),
    )
    return runtime, bus, journal


async def test_full_vertical_with_real_effects(git_repo, data_dir):
    runtime, bus, journal = make_runtime(
        git_repo, data_dir, [plan_json(content=NEW_CONTENT)])

    snapshot = await runtime.start_planning(
        repo_path=git_repo,
        task_description='Change the greeting returned by hello.py from "Hello" to "Hello Stratum".',
    )
    assert snapshot.status.value == "APPROVAL_REQUIRED"
    assert snapshot.plan is not None and len(snapshot.plan.steps) == 4

    result = await runtime.decide_and_execute(snapshot.execution_id)

    # 1. Repository actually changed as requested.
    assert (git_repo / "hello.py").read_text() == NEW_CONTENT

    # 2. Verification command actually ran (pytest passed).
    assert result.status is ExecutionStatus.COMPLETED
    last = result.observations[-1]
    assert last["ok"] and last["exit_code"] == 0

    # 3. Git shows the intended change.
    diff = subprocess.run(
        ["git", "-C", str(git_repo), "diff"], capture_output=True, text=True
    ).stdout
    assert '"Hello Stratum"' in diff

    # 4. Complete lifecycle event chain exists, ordered, causally linked.
    types = [e.event_type for e in bus.events]
    for expected in ("task.created", "task.planning_started", "ai.requested",
                     "ai.responded", "plan.generated", "approval.requested",
                     "approval.granted", EXECUTION_STARTED):
        assert expected in types
    assert types.index("approval.granted") < types.index(EXECUTION_STARTED)
    assert types[-1] == "task.completed"

    sequences = [e.sequence for e in bus.events]
    assert sequences == sorted(sequences) and len(set(sequences)) == len(sequences)
    correlation = bus.events[0].correlation_id
    assert all(e.correlation_id == correlation for e in bus.events)
    for i, event in enumerate(bus.events[1:], start=1):
        assert event.causation_id == bus.events[i - 1].event_id

    # 5. Tool boundary events wrap every invocation.
    started = [e for e in bus.events if e.event_type == TOOL_STARTED]
    completed = [e for e in bus.events if e.event_type == TOOL_COMPLETED]
    assert len(started) == 4 and len(completed) == 4
    artifacts = [e for e in bus.events if e.event_type == ARTIFACT_CREATED]
    assert len(artifacts) == 2
    assert {a.payload["path"] for a in artifacts} == {"hello.py", "test_hello.py"}
    hello_artifact = next(a for a in artifacts if a.payload["path"] == "hello.py")
    assert '+    return "Hello Stratum"' in hello_artifact.payload["diff"]

    # 6. Durable journal holds the same authoritative history.
    jevents = journal.read_execution(snapshot.execution_id)
    assert len(jevents) == len(bus.events)


async def test_replay_from_journal_reconstructs_execution(git_repo, data_dir):
    runtime, _, journal = make_runtime(
        git_repo, data_dir, [plan_json(content=NEW_CONTENT)])

    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")
    await runtime.decide_and_execute(snapshot.execution_id)

    from stratum.replay import fold, render_narrative

    replayed = fold(journal.read_execution(snapshot.execution_id))
    assert replayed.status == "COMPLETED"
    assert replayed.description == "t"
    assert len(replayed.plan_steps) == 4
    assert replayed.approval == "granted"
    assert [c["state"] for c in replayed.tool_calls] == ["completed"] * 4
    narrative = render_narrative(replayed)
    assert "[+]" in narrative and "Status:   COMPLETED" in narrative


async def test_rejection_blocks_all_side_effects(git_repo, data_dir):
    original = (git_repo / "hello.py").read_text()
    runtime, bus, _ = make_runtime(git_repo, data_dir,
                                   [plan_json(content="x")], decision="rejected")
    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")
    result = await runtime.decide_and_execute(snapshot.execution_id)

    assert result.status is ExecutionStatus.REJECTED
    assert (git_repo / "hello.py").read_text() == original  # untouched
    types = [e.event_type for e in bus.events]
    assert "execution.started" not in types
    assert types[-1] == "approval.rejected"


async def test_approval_boundary_is_structural(git_repo, data_dir):
    runtime, _, _ = make_runtime(git_repo, data_dir, [plan_json(content="x")])
    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")

    # First decision consumes the pending approval.
    await runtime.decide_and_execute(snapshot.execution_id)
    with pytest.raises(Exception, match="cannot resolve approval"):
        await runtime.decide_and_execute(snapshot.execution_id)


async def test_materialization_uses_second_real_provider_call(git_repo, data_dir):
    # Plan carries NO content -> forces grounded materialization at exec time.
    bare_write_plan = json.dumps({
        "rationale": "r",
        "steps": [
            {"description": "Read hello.py", "action_type": "read_file",
             "path": "hello.py"},
            {"description": "Change to Hello Stratum", "action_type": "write_file",
             "path": "hello.py", "content_summary": 'greeting returns Hello Stratum'},
            {"description": "Update the test expectation",
             "action_type": "write_file", "path": "test_hello.py",
             "content_summary": 'assert greeting() == "Hello Stratum"',
             "content": 'from hello import greeting\n\n\ndef test_greeting():\n'
                        '    assert greeting() == "Hello Stratum"\n'},
            {"description": "Run tests", "action_type": "run_command",
             "command": f"{sys.executable} -m pytest -q"},
        ],
    })

    sa = ScriptedAdapter(responder=lambda req: (
        scripted_json_response(bare_write_plan)
        if req.metadata.get("purpose") == "planning"
        else scripted_json_response(NEW_CONTENT)
    ))
    bus = InMemoryEventPublisher()
    runtime = StratumRuntime(
        adapter=sa,
        model="scripted-model",
        publisher=bus,
        approval_policy=PreDecidedApprovalPolicy("granted"),
    )

    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")
    assert snapshot.status.value == "APPROVAL_REQUIRED"
    result = await runtime.decide_and_execute(snapshot.execution_id)

    assert result.status is ExecutionStatus.COMPLETED
    assert (git_repo / "hello.py").read_text() == NEW_CONTENT

    requested = [e for e in bus.events if e.event_type == AI_REQUESTED]
    purposes = [e.payload["purpose"] for e in requested]
    assert purposes == ["planning", "materialize_write"]
    # The materialization request was grounded in the actual read contents.
    mat_request = sa.requests[1]
    assert "# Current file content" in mat_request.messages[1].content
    assert 'return "Hello"' in mat_request.messages[1].content


async def test_failing_verification_fails_task(git_repo, data_dir):
    failing = json.dumps({
        "rationale": "r",
        "steps": [
            {"description": "Run failing check", "action_type": "run_command",
             "command": "false"},
            {"description": "Never reached", "action_type": "read_file",
             "path": "hello.py"},
        ],
    })
    runtime, bus, _ = make_runtime(git_repo, data_dir, [failing])
    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")
    result = await runtime.decide_and_execute(snapshot.execution_id)

    assert result.status is ExecutionStatus.FAILED
    types = [e.event_type for e in bus.events]
    assert "tool.completed" in types      # the command DID run
    assert "task.failed" in types         # its exit code failed the task
    assert types.count("tool.started") == 1  # fail-stop: second step skipped


async def test_cancel_before_execution_has_no_effects(git_repo, data_dir):
    runtime, bus, _ = make_runtime(git_repo, data_dir, [plan_json(content="x")])
    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")
    result = await runtime.cancel(snapshot.execution_id)

    assert result.status is ExecutionStatus.CANCELLED
    assert "execution.started" not in [e.event_type for e in bus.events]


async def test_invalid_model_output_fails_before_approval(git_repo, data_dir):
    runtime, bus, _ = make_runtime(git_repo, data_dir, ["this is prose, not json"])
    snapshot = await runtime.start_planning(repo_path=git_repo, task_description="t")

    assert snapshot.status is ExecutionStatus.FAILED
    assert "invalid plan" in snapshot.error
    types = [e.event_type for e in bus.events]
    assert "approval.requested" not in types
