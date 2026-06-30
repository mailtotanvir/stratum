import subprocess

from fastapi.testclient import TestClient

from app.main import app
from app.routes.runtime import get_runtime_workspace_service
from app.services.runtime_workspace_service import RuntimeWorkspaceService


def test_runtime_workspace_binding_route(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("workspace", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "commit.gpgSign=false", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    service = RuntimeWorkspaceService(tmp_path)
    app.dependency_overrides[get_runtime_workspace_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.get("/runtime/workspaces/binding")
        assert response.status_code == 200
        payload = response.json()
        assert payload["workspace"]["name"] == "default"
        assert payload["repository"]["is_git_repository"] is True
        assert payload["runtime_execution_allowed"] is True
        assert payload["workspace_artifact_count"] == 0
    finally:
        app.dependency_overrides.clear()
