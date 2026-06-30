from fastapi.testclient import TestClient

from app.main import app
from app.routes.runtime import get_runtime_workspace_service
from app.services.runtime_workspace_service import RuntimeWorkspaceService


def test_runtime_workspace_routes(tmp_path) -> None:
    service = RuntimeWorkspaceService(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    app.dependency_overrides[get_runtime_workspace_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.get("/runtime/workspaces")
        assert response.status_code == 200
        payload = response.json()
        assert [item["name"] for item in payload] == ["default"]

        response = client.post(
            "/runtime/workspaces",
            json={"name": "other", "root_path": str(other)},
        )
        assert response.status_code == 200
        workspace = response.json()
        assert workspace["name"] == "other"
        assert workspace["active"] is False

        response = client.get("/runtime/workspaces/active")
        assert response.status_code == 200
        assert response.json()["name"] == "default"

        response = client.post(
            f"/runtime/workspaces/{workspace['workspace_id']}/activate",
        )
        assert response.status_code == 200
        assert response.json()["name"] == "other"

        response = client.get("/runtime/workspaces/active")
        assert response.status_code == 200
        assert response.json()["name"] == "other"
    finally:
        app.dependency_overrides.clear()

