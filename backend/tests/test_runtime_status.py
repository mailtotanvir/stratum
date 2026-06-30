from fastapi.testclient import TestClient

from app.main import app
from app.services.event_service import event_service
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService
from app.services.tool_registry_service import tool_registry_service


def test_runtime_status(tmp_path) -> None:
    runtime_session_service.set_db_path(tmp_path / "sessions.db")
    event_service.set_trace_store(TraceService(tmp_path / "events.db"))
    tool_registry_service.set_db_path(tmp_path / "tools.db")
    tool_registry_service.register_tool(
        name="final_answer",
        description="Return the final response",
        enabled=True,
        parameters=[],
    )
    runtime_session_service.create_session("task-1")

    client = TestClient(app)
    response = client.get("/runtime/status")

    assert response.status_code == 200
    body = response.json()
    assert body["backend_version"] == "0.1.0"
    assert body["provider_status"] in {
        "ready",
        "unconfigured",
        "configuration_error",
    }
    assert body["registered_tools"] == ["final_answer"]
    assert body["registered_providers"]
    assert body["active_sessions"] == 1
