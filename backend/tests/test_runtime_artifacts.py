from fastapi.testclient import TestClient

from app.main import app


def create_artifact(client: TestClient, path: str = "artifacts/task-123/report.md"):
    return client.post(
        "/artifacts",
        json={
            "path": path,
            "kind": "report",
        },
    )


def create_runtime_session(client: TestClient, task_id: str) -> str:
    response = client.post(f"/runtime/tasks/{task_id}/run")
    assert response.status_code == 200
    sessions = client.get("/runtime/sessions", params={"task_id": task_id}).json()
    return sessions[0]["id"]


def test_attach_artifact_to_runtime_task() -> None:
    client = TestClient(app)
    artifact = create_artifact(client)
    artifact_id = artifact.json()["id"]

    response = client.post(f"/runtime/tasks/task-123/artifacts/{artifact_id}")

    assert artifact.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-123",
        "artifact_id": artifact_id,
        "session_id": None,
        "attached": True,
    }


def test_duplicate_runtime_artifact_attach_returns_409() -> None:
    client = TestClient(app)
    artifact_id = create_artifact(client).json()["id"]

    first = client.post(f"/runtime/tasks/task-123/artifacts/{artifact_id}")
    second = client.post(f"/runtime/tasks/task-123/artifacts/{artifact_id}")

    assert first.status_code == 200
    assert second.status_code == 409


def test_unknown_runtime_artifact_attach_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/runtime/tasks/task-123/artifacts/missing-artifact")

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found: missing-artifact"


def test_list_attached_runtime_artifacts() -> None:
    client = TestClient(app)
    first_artifact = create_artifact(
        client,
        path="artifacts/task-123/report.md",
    ).json()
    second_artifact = create_artifact(
        client,
        path="artifacts/task-123/summary.md",
    ).json()
    client.post(f"/runtime/tasks/task-123/artifacts/{first_artifact['id']}")
    client.post(f"/runtime/tasks/task-123/artifacts/{second_artifact['id']}")

    response = client.get("/runtime/tasks/task-123/artifacts")

    assert response.status_code == 200
    attached = response.json()
    attached_by_id = {
        record["artifact_id"]: record
        for record in attached
    }
    assert set(attached_by_id) == {first_artifact["id"], second_artifact["id"]}
    assert attached_by_id[first_artifact["id"]]["task_id"] == "task-123"
    assert attached_by_id[first_artifact["id"]]["session_id"] is None
    assert attached_by_id[first_artifact["id"]]["artifact"] == first_artifact
    assert attached_by_id[first_artifact["id"]]["attached_at"] is not None


def test_runtime_artifact_attached_appears_in_trace() -> None:
    client = TestClient(app)
    artifact_id = create_artifact(client).json()["id"]

    attach_response = client.post(f"/runtime/tasks/task-123/artifacts/{artifact_id}")
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert attach_response.status_code == 200
    assert trace_response.status_code == 200
    events = trace_response.json()
    assert [event["type"] for event in events] == ["runtime_artifact_attached"]
    assert events[0]["metadata"]["task_id"] == "task-123"
    assert events[0]["metadata"]["artifact_id"] == artifact_id


def test_runtime_artifact_filtering_by_task_id_works() -> None:
    client = TestClient(app)
    first_artifact_id = create_artifact(
        client,
        path="artifacts/task-123/report.md",
    ).json()["id"]
    second_artifact_id = create_artifact(
        client,
        path="artifacts/task-456/report.md",
    ).json()["id"]
    client.post(f"/runtime/tasks/task-123/artifacts/{first_artifact_id}")
    client.post(f"/runtime/tasks/task-456/artifacts/{second_artifact_id}")

    response = client.get("/runtime/tasks/task-123/artifacts")

    assert response.status_code == 200
    assert [record["artifact_id"] for record in response.json()] == [
        first_artifact_id,
    ]


def test_attach_artifact_with_session_id() -> None:
    client = TestClient(app)
    session_id = create_runtime_session(client, "task-123")
    artifact_id = create_artifact(client).json()["id"]

    response = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": session_id},
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-123",
        "artifact_id": artifact_id,
        "session_id": session_id,
        "attached": True,
    }


def test_attach_artifact_unknown_session_id_returns_404() -> None:
    client = TestClient(app)
    artifact_id = create_artifact(client).json()["id"]

    response = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": "missing-session"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"


def test_attach_artifact_session_task_mismatch_returns_409() -> None:
    client = TestClient(app)
    session_id = create_runtime_session(client, "task-456")
    artifact_id = create_artifact(client).json()["id"]

    response = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": session_id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Runtime session does not belong to task: {session_id}"
    )


def test_duplicate_same_task_artifact_session_returns_409() -> None:
    client = TestClient(app)
    session_id = create_runtime_session(client, "task-123")
    artifact_id = create_artifact(client).json()["id"]

    first = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": session_id},
    )
    second = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": session_id},
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_same_artifact_can_attach_to_same_task_under_different_sessions() -> None:
    client = TestClient(app)
    first_session_id = create_runtime_session(client, "task-123")
    second_session_id = create_runtime_session(client, "task-123")
    artifact_id = create_artifact(client).json()["id"]

    first = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": first_session_id},
    )
    second = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": second_session_id},
    )

    assert first.status_code == 200
    assert second.status_code == 200


def test_list_task_artifacts_filtered_by_session_id() -> None:
    client = TestClient(app)
    first_session_id = create_runtime_session(client, "task-123")
    second_session_id = create_runtime_session(client, "task-123")
    first_artifact_id = create_artifact(
        client,
        path="artifacts/task-123/first.md",
    ).json()["id"]
    second_artifact_id = create_artifact(
        client,
        path="artifacts/task-123/second.md",
    ).json()["id"]
    client.post(
        f"/runtime/tasks/task-123/artifacts/{first_artifact_id}",
        params={"session_id": first_session_id},
    )
    client.post(
        f"/runtime/tasks/task-123/artifacts/{second_artifact_id}",
        params={"session_id": second_session_id},
    )

    response = client.get(
        "/runtime/tasks/task-123/artifacts",
        params={"session_id": first_session_id},
    )

    assert response.status_code == 200
    assert [record["artifact_id"] for record in response.json()] == [
        first_artifact_id,
    ]
    assert response.json()[0]["session_id"] == first_session_id


def test_runtime_artifact_trace_event_includes_session_id() -> None:
    client = TestClient(app)
    session_id = create_runtime_session(client, "task-123")
    artifact_id = create_artifact(client).json()["id"]

    response = client.post(
        f"/runtime/tasks/task-123/artifacts/{artifact_id}",
        params={"session_id": session_id},
    )
    trace_response = client.get(
        "/trace",
        params={"task_id": "task-123", "type": "runtime_artifact_attached"},
    )

    assert response.status_code == 200
    assert trace_response.status_code == 200
    events = trace_response.json()
    assert len(events) == 1
    assert events[0]["metadata"]["session_id"] == session_id
