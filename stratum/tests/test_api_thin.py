from __future__ import annotations

import json
import sys

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from stratum.adapters.scripted import ScriptedAdapter, scripted_json_response  # noqa: E402
from stratum.api import RuntimeHolder, create_app  # noqa: E402
from stratum.approval import PreDecidedApprovalPolicy  # noqa: E402
from stratum.engine import StratumRuntime  # noqa: E402
from stratum.journal import FileEventJournal, JournalPublisher  # noqa: E402
from stratum.publisher import CompositeEventPublisher, InMemoryEventPublisher  # noqa: E402


@pytest.fixture
def client(git_repo, data_dir):
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
    app = create_app(RuntimeHolder(
        runtime=runtime,
        read_events=lambda eid: journal.read_execution(eid),
    ))
    return TestClient(app), git_repo


def test_api_full_flow(client):
    http, git_repo = client
    resp = http.post("/tasks", json={
        "repo_path": str(git_repo),
        "task_description": 'change greeting to "Hello Stratum"',
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "APPROVAL_REQUIRED"
    assert body["plan"]["steps"][1]["action_type"] == "write_file"
    eid = body["execution_id"]

    events_before = http.get(f"/tasks/{eid}/events").json()
    assert len(events_before) >= 5

    resp = http.post(f"/tasks/{eid}/approve", json={"decider": "api-test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert 'return "Hello Stratum"' in (git_repo / "hello.py").read_text()

    replay = http.get(f"/tasks/{eid}/replay").json()
    assert replay["status"] == "COMPLETED"

    events_after = http.get(f"/tasks/{eid}/events").json()
    assert len(events_after) > len(events_before)


def test_api_reject(client):
    http, git_repo = client
    resp = http.post("/tasks", json={
        "repo_path": str(git_repo),
        "task_description": "t",
    })
    eid = resp.json()["execution_id"]
    resp = http.post(f"/tasks/{eid}/reject", json={"decider": "api-test"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"


def test_api_unknown_execution_404(client):
    http, _ = client
    assert http.get("/tasks/exe_does_not_exist").status_code == 404
