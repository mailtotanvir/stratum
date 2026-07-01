from fastapi.testclient import TestClient

from app.main import app
from app.services.artifact_service import ArtifactService
from app.routes import transformation_session as transformation_session_routes
from app.services.proposal_service import ProposalService
from app.services.transformation_session_service import TransformationSessionService
from app.services.task_service import TaskService


def test_create_transformation_session_builds_governed_artifacts(tmp_path) -> None:
    tasks = TaskService(tmp_path / "tasks.db")
    proposals = ProposalService(tmp_path / "proposals.db")
    artifacts = ArtifactService(tmp_path / "artifacts.db")
    transformation_session_routes.transformation_session_service = TransformationSessionService(
        tasks=tasks,
        proposals=proposals,
        artifacts=artifacts,
    )
    client = TestClient(app)

    response = client.post(
        "/runtime/transformation-sessions",
        json={
            "title": "Repository update",
            "objective": "Change the API response shape.",
            "specification": "1. Attach spec.\n2. Propose patch.\n3. Request approval.",
            "context_markdown": "# Context\nExisting runtime flow.",
            "validation_command": "git diff --check",
            "affected_files": ["backend/app/main.py"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "completed"
    assert payload["proposal"]["status"] == "proposed"
    assert payload["patch"]["status"] == "proposed"
    assert payload["patch"]["affected_files"] == ["backend/app/main.py"]
    assert payload["validation_command"] == "git diff --check"
    assert payload["artifacts"]
    assert any(artifact["label"] == "specification" for artifact in payload["artifacts"])
    assert any(artifact["label"] == "patch-proposal" for artifact in payload["artifacts"])
    assert payload["summary"].startswith("Prepared 1 file targets")

    list_response = client.get("/runtime/transformation-sessions")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["transformation_id"] == payload["transformation_id"]


def test_unknown_transformation_session_returns_404(tmp_path) -> None:
    transformation_session_routes.transformation_session_service = TransformationSessionService(
        tasks=TaskService(tmp_path / "tasks.db"),
        proposals=ProposalService(tmp_path / "proposals.db"),
        artifacts=ArtifactService(tmp_path / "artifacts.db"),
    )
    client = TestClient(app)

    response = client.get("/runtime/transformation-sessions/missing")

    assert response.status_code == 404
