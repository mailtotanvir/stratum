from __future__ import annotations

import asyncio
import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from stratum.adapters.scripted import ScriptedAdapter, scripted_json_response  # noqa: E402
from stratum.api import RuntimeHolder  # noqa: E402
from stratum.approval import PreDecidedApprovalPolicy  # noqa: E402
from stratum.engine import StratumRuntime  # noqa: E402
from stratum.store import SqliteEventStore  # noqa: E402
from stratum.journal import FileEventJournal, JournalPublisher  # noqa: E402
from stratum.publisher import (  # noqa: E402
    CompositeEventPublisher,
    InMemoryEventPublisher,
)
from stratum.webui import create_web_app, journal_list_executions  # noqa: E402


@pytest.fixture
def web_client(git_repo, data_dir):
    bus = InMemoryEventPublisher()
    journal = FileEventJournal(data_dir / "events.ndjson")
    runtime = StratumRuntime(
        adapter=ScriptedAdapter(responder=lambda req: scripted_json_response(
            json.dumps({
                "rationale": "r",
                "steps": [
                    {"description": "read", "action_type": "read_file",
                     "path": "hello.py"},
                    {"description": "write", "action_type": "write_file",
                     "path": "hello.py",
                     "content": 'def greeting():\n    return "Hello Stratum"\n'},
                ],
            })
        )),
        model="scripted-model",
        publisher=CompositeEventPublisher(bus, JournalPublisher(journal)),
        approval_policy=PreDecidedApprovalPolicy("granted"),
    )
    holder = RuntimeHolder(
        runtime=runtime,
        read_events=journal.read_execution,
        list_executions=journal_list_executions(journal),
    )
    app = create_web_app(holder, meta={
        "broker": False, "provider": "scripted", "model": "scripted-model"})
    return TestClient(app), git_repo


def test_index_html_served(web_client):
    http, _ = web_client
    resp = http.get("/")
    assert resp.status_code == 200
    assert "Stratum" in resp.text
    assert "app.js" in resp.text


def test_healthz_reports_meta(web_client):
    http, _ = web_client
    body = http.get("/healthz").json()
    assert body["ok"] is True
    assert body["broker"] is False
    assert body["model"] == "scripted-model"


def test_full_uat_flow_and_history(web_client):
    http, git_repo = web_client

    resp = http.post("/tasks", json={
        "repo_path": str(git_repo),
        "task_description": 'change greeting to "Hello Stratum"',
    })
    eid = resp.json()["execution_id"]

    # Plan arrives; operator approves via API (the UI does exactly this).
    assert resp.json()["status"] == "APPROVAL_REQUIRED"
    resp = http.post(f"/tasks/{eid}/approve", json={"decider": "web-operator"})
    assert resp.json()["status"] == "COMPLETED"

    # History lists the finished execution with folded status.
    rows = http.get("/executions").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["execution_id"] == eid
    assert row["status"] == "COMPLETED"
    assert row["approval"] == "granted"
    assert row["event_count"] > 5
    assert row["started_at"] and row["ended_at"]


def test_executions_empty_without_journal(git_repo, tmp_path):
    journal = FileEventJournal(tmp_path / "empty.ndjson")
    holder = RuntimeHolder(
        runtime=None, read_events=journal.read_execution,
        list_executions=journal_list_executions(journal))
    http = TestClient(create_web_app(holder))
    assert http.get("/executions").json() == []


def test_approval_survives_server_restart(git_repo, data_dir):
    """The UAT killer scenario: plan arrives, server dies, operator still
    approves from the console after restart."""
    import sys

    db_path = data_dir / "stratum.db"

    def scripted_plan_response():
        return scripted_json_response(json.dumps({
            "rationale": "r",
            "steps": [
                {"description": "write", "action_type": "write_file",
                 "path": "hello.py",
                 "content": 'def greeting():\n    return "Hello Stratum"\n'},
                {"description": "update test", "action_type": "write_file",
                 "path": "test_hello.py",
                 "content": 'from hello import greeting\n\n\ndef test_greeting():\n'
                            '    assert greeting() == "Hello Stratum"\n'},
                {"description": "verify", "action_type": "run_command",
                 "command": f"{sys.executable} -m pytest -q"},
            ],
        }))

    class PlanOnceAdapter:
        """Serves the plan once; refuses any later AI call."""

        provider_name = "scripted"
        endpoint_host = "scripted.local"

        async def generate(self, request):
            if request.metadata.get("purpose") != "planning":
                raise AssertionError("no AI calls expected on execute path")
            return scripted_plan_response()

    # --- first server process: submit task, get pending approval ----------
    store1 = SqliteEventStore(db_path)
    runtime1 = StratumRuntime(
        adapter=PlanOnceAdapter(), model="scripted-model",
        publisher=InMemoryEventPublisher(),
        approval_policy=PreDecidedApprovalPolicy("granted"),
        store=store1,
    )
    app1 = create_web_app(RuntimeHolder(
        runtime=runtime1, read_events=store1.read_execution,
        list_executions=lambda: []))
    client1 = TestClient(app1)

    body = client1.post("/tasks", json={
        "repo_path": str(git_repo), "task_description": "t"}).json()
    eid = body["execution_id"]
    assert body["status"] == "APPROVAL_REQUIRED"
    del client1, app1, runtime1, store1  # server dies

    # --- second server process over the same database ----------------------
    from stratum.cli import _store_list_executions

    store2 = SqliteEventStore(db_path)

    class DeadAdapter:
        provider_name = "scripted"
        endpoint_host = "dead.local"

        async def generate(self, request):
            raise AssertionError("restart must not need the AI again")

    runtime2 = StratumRuntime(
        adapter=DeadAdapter(), model="m",
        publisher=InMemoryEventPublisher(),
        approval_policy=PreDecidedApprovalPolicy("granted"),
        store=store2,
    )
    resumed = asyncio.run(runtime2.resume_pending())
    assert [s.execution_id for s in resumed] == [eid]

    holder2 = RuntimeHolder(
        runtime=runtime2, read_events=store2.read_execution,
        list_executions=_store_list_executions(store2))
    client2 = TestClient(create_web_app(holder2))

    # History shows the pending execution.
    rows = client2.get("/executions").json()
    assert any(r["execution_id"] == eid and r["status"] == "APPROVAL_REQUIRED"
               for r in rows)

    # Operator approves in the restarted console.
    result = client2.post(f"/tasks/{eid}/approve",
                          json={"decider": "web-operator"}).json()
    assert result["status"] == "COMPLETED"
    assert 'return "Hello Stratum"' in (git_repo / "hello.py").read_text()
