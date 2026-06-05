from fastapi.testclient import TestClient

from app.main import app


def test_create_artifact_persists() -> None:
    client = TestClient(app)

    response = client.post(
        "/artifacts",
        json={
            "path": "artifacts/task-123/report.md",
            "kind": "report",
            "task_id": "task-123",
            "metadata": {"format": "markdown"},
        },
    )

    assert response.status_code == 200
    artifact = response.json()
    get_response = client.get(f"/artifacts/{artifact['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == artifact
    assert artifact["path"] == "artifacts/task-123/report.md"
    assert artifact["kind"] == "report"
    assert artifact["task_id"] == "task-123"
    assert artifact["proposal_id"] is None
    assert artifact["metadata"] == {"format": "markdown"}


def test_artifact_created_appears_in_trace() -> None:
    client = TestClient(app)

    response = client.post(
        "/artifacts",
        json={
            "path": "logs/task-123/runtime.log",
            "kind": "log",
            "task_id": "task-123",
        },
    )
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert response.status_code == 200
    assert trace_response.status_code == 200
    events = trace_response.json()
    assert [event["type"] for event in events] == ["artifact_created"]
    assert events[0]["metadata"]["artifact_id"] == response.json()["id"]
    assert events[0]["metadata"]["task_id"] == "task-123"
    assert events[0]["metadata"]["path"] == "logs/task-123/runtime.log"
    assert events[0]["metadata"]["kind"] == "log"


def test_list_artifacts() -> None:
    client = TestClient(app)

    first = client.post(
        "/artifacts",
        json={"path": "artifacts/first.txt", "kind": "file"},
    )
    second = client.post(
        "/artifacts",
        json={"path": "artifacts/second.patch", "kind": "patch"},
    )
    response = client.get("/artifacts")

    assert first.status_code == 200
    assert second.status_code == 200
    assert response.status_code == 200
    artifact_ids = {artifact["id"] for artifact in response.json()}
    assert artifact_ids == {first.json()["id"], second.json()["id"]}


def test_filter_artifacts_by_task_id() -> None:
    client = TestClient(app)

    expected = client.post(
        "/artifacts",
        json={
            "path": "artifacts/task-123/summary.md",
            "kind": "summary",
            "task_id": "task-123",
        },
    )
    client.post(
        "/artifacts",
        json={
            "path": "artifacts/task-456/summary.md",
            "kind": "summary",
            "task_id": "task-456",
        },
    )
    response = client.get("/artifacts", params={"task_id": "task-123"})

    assert response.status_code == 200
    assert response.json() == [expected.json()]


def test_filter_artifacts_by_proposal_id() -> None:
    client = TestClient(app)

    expected = client.post(
        "/artifacts",
        json={
            "path": "artifacts/proposal-123/report.md",
            "kind": "report",
            "proposal_id": "proposal-123",
        },
    )
    client.post(
        "/artifacts",
        json={
            "path": "artifacts/proposal-456/report.md",
            "kind": "report",
            "proposal_id": "proposal-456",
        },
    )
    response = client.get("/artifacts", params={"proposal_id": "proposal-123"})

    assert response.status_code == 200
    assert response.json() == [expected.json()]


def test_filter_artifacts_by_kind() -> None:
    client = TestClient(app)

    expected = client.post(
        "/artifacts",
        json={"path": "artifacts/task-123/changes.patch", "kind": "patch"},
    )
    client.post(
        "/artifacts",
        json={"path": "artifacts/task-123/report.md", "kind": "report"},
    )
    response = client.get("/artifacts", params={"kind": "patch"})

    assert response.status_code == 200
    assert response.json() == [expected.json()]


def test_unknown_artifact_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/artifacts/missing-artifact")

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found: missing-artifact"


def test_invalid_artifact_kind_rejected() -> None:
    client = TestClient(app)

    response = client.post(
        "/artifacts",
        json={
            "path": "artifacts/task-123/output.bin",
            "kind": "binary",
        },
    )

    assert response.status_code == 422
