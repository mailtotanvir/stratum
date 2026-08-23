"""Acceptance test: the full vertical against a REAL configured AI provider.

Real task -> real repository -> real provider API -> real structured plan ->
real approval -> real tool execution -> real repository mutation -> real
verification command -> durable events -> replay.

Runs automatically when a provider is configured (STRATUM_PROVIDER_BASE_URL /
OPENAI_API_BASE plus an API key). Skips cleanly otherwise.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from stratum.adapters.openai_compatible import OpenAICompatibleAdapter
from stratum.approval import ApprovalRecord
from stratum.engine import ExecutionStatus, StratumRuntime
from stratum.journal import FileEventJournal, JournalPublisher
from stratum.planning import Planner
from stratum.publisher import CompositeEventPublisher, InMemoryEventPublisher
from stratum.replay import fold

pytestmark = pytest.mark.acceptance_provider


def _provider_config():
    from stratum.config import resolve_provider

    model = os.environ.get("STRATUM_TEST_MODEL")
    config = resolve_provider(model=model)
    if config is None or not config.model:
        pytest.skip("no real provider configured; acceptance path not exercised")
    return config.base_url, config.api_key, config.model


async def test_real_provider_transforms_real_repository(git_repo, data_dir):
    base_url, api_key, model = _provider_config()
    adapter = OpenAICompatibleAdapter(base_url=base_url, api_key=api_key)

    bus = InMemoryEventPublisher()
    journal = FileEventJournal(data_dir / "events.ndjson")
    runtime = StratumRuntime(
        adapter=adapter,
        model=model,
        publisher=CompositeEventPublisher(bus, JournalPublisher(journal)),
        approval_policy=_Approver(),
        planner=Planner(model=model),
    )

    snapshot = await runtime.start_planning(
        repo_path=git_repo,
        task_description=(
            'Change the greeting returned by hello.py from "Hello" to '
            '"Hello Stratum" and update the test accordingly.'
        ),
        selected_files=["hello.py", "test_hello.py"],
        markdown_context=(
            "Environment notes:\n"
            "- Verify changes by running exactly: "
            f"{sys.executable} -m pytest -q\n"
            "(the plain `pytest` binary is not on PATH)."
        ),
    )

    # A real model produced a real structured plan.
    assert snapshot.plan is not None, snapshot.error
    assert len(snapshot.plan.steps) >= 2
    assert any(s.action_type == "write_file" for s in snapshot.plan.steps)
    assert snapshot.status.value == "APPROVAL_REQUIRED"

    result = await runtime.decide_and_execute(snapshot.execution_id)

    assert result.status is ExecutionStatus.COMPLETED, result.error
    assert 'return "Hello Stratum"' in (git_repo / "hello.py").read_text()

    diff = subprocess.run(
        ["git", "-C", str(git_repo), "diff"], capture_output=True, text=True
    ).stdout
    assert '"Hello Stratum"' in diff

    # Provider/model metadata recorded in events; never secrets.
    ai_events = [e for e in bus.events if e.event_type.startswith("ai.")]
    assert ai_events
    for event in bus.events:
        blob = event.to_json().decode()
        assert api_key not in blob

    # Replay reconstructs without AI or effects.
    replayed = fold(journal.read_execution(result.execution_id))
    assert replayed.status == "COMPLETED"
    await adapter.aclose()


class _Approver:
    """Programmatic operator decision for the automated harness.

    The interactive human prompt is exercised by the CLI; this record keeps
    the automated run non-blocking while still crossing the real approval
    boundary in the engine.
    """

    def decide(self, execution_id, plan):
        return ApprovalRecord("granted", "acceptance-harness", plan.id)
