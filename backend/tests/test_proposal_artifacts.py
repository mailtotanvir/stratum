from fastapi.testclient import TestClient

from app.main import app


def create_proposal(client: TestClient) -> dict:
    response = client.post(
        "/proposals",
        json={
            "title": "Review artifact",
            "body": "Review the attached artifact.",
        },
    )
    assert response.status_code == 200
    return response.json()


def create_artifact(client: TestClient) -> dict:
    response = client.post(
        "/artifacts",
        json={
            "path": "artifacts/proposal/report.md",
            "kind": "report",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_attach_artifact_to_proposal() -> None:
    client = TestClient(app)
    proposal = create_proposal(client)
    artifact = create_artifact(client)

    response = client.post(
        f"/proposals/{proposal['id']}/artifacts/{artifact['id']}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": proposal["id"],
        "artifact_id": artifact["id"],
        "attached": True,
    }


def test_duplicate_proposal_artifact_attach_returns_409() -> None:
    client = TestClient(app)
    proposal = create_proposal(client)
    artifact = create_artifact(client)

    first = client.post(f"/proposals/{proposal['id']}/artifacts/{artifact['id']}")
    second = client.post(f"/proposals/{proposal['id']}/artifacts/{artifact['id']}")

    assert first.status_code == 200
    assert second.status_code == 409


def test_unknown_proposal_artifact_attach_returns_404() -> None:
    client = TestClient(app)
    artifact = create_artifact(client)

    response = client.post(f"/proposals/missing-proposal/artifacts/{artifact['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Proposal not found: missing-proposal"


def test_unknown_artifact_proposal_attach_returns_404() -> None:
    client = TestClient(app)
    proposal = create_proposal(client)

    response = client.post(f"/proposals/{proposal['id']}/artifacts/missing-artifact")

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found: missing-artifact"


def test_list_proposal_artifacts() -> None:
    client = TestClient(app)
    proposal = create_proposal(client)
    first = create_artifact(client)
    second = client.post(
        "/artifacts",
        json={
            "path": "artifacts/proposal/summary.md",
            "kind": "summary",
        },
    ).json()
    client.post(f"/proposals/{proposal['id']}/artifacts/{first['id']}")
    client.post(f"/proposals/{proposal['id']}/artifacts/{second['id']}")

    response = client.get(f"/proposals/{proposal['id']}/artifacts")

    assert response.status_code == 200
    attached_by_id = {
        record["artifact_id"]: record
        for record in response.json()
    }
    assert set(attached_by_id) == {first["id"], second["id"]}
    assert attached_by_id[first["id"]]["proposal_id"] == proposal["id"]
    assert attached_by_id[first["id"]]["artifact"] == first
    assert attached_by_id[first["id"]]["attached_at"] is not None


def test_proposal_artifact_attached_appears_in_trace() -> None:
    client = TestClient(app)
    proposal = create_proposal(client)
    artifact = create_artifact(client)

    attach_response = client.post(
        f"/proposals/{proposal['id']}/artifacts/{artifact['id']}"
    )
    trace_response = client.get("/trace", params={"proposal_id": proposal["id"]})

    assert attach_response.status_code == 200
    assert trace_response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "proposal_artifact_attached" in event_types


def test_trace_filtered_by_proposal_id_includes_attachment_event() -> None:
    client = TestClient(app)
    first_proposal = create_proposal(client)
    second_proposal = create_proposal(client)
    first_artifact = create_artifact(client)
    second_artifact = client.post(
        "/artifacts",
        json={
            "path": "artifacts/proposal/other.md",
            "kind": "report",
        },
    ).json()
    client.post(f"/proposals/{first_proposal['id']}/artifacts/{first_artifact['id']}")
    client.post(
        f"/proposals/{second_proposal['id']}/artifacts/{second_artifact['id']}"
    )

    response = client.get(
        "/trace",
        params={
            "proposal_id": first_proposal["id"],
            "type": "proposal_artifact_attached",
        },
    )

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["metadata"]["proposal_id"] == first_proposal["id"]
    assert events[0]["metadata"]["artifact_id"] == first_artifact["id"]
