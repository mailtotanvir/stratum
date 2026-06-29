from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_execution_diagnostics_service import (
    AgentExecutionDiagnosticsService,
)


client = TestClient(app)


def test_agent_execution_diagnostics_route_returns_200() -> None:
    response = client.get("/runtime/agent-execution/diagnostics")

    assert response.status_code == 200


def test_diagnostics_confirm_execution_services_are_ready() -> None:
    body = client.get("/runtime/agent-execution/diagnostics").json()

    assert body["agent_execution_service_ready"] is True
    assert body["provider_execution_service_ready"] is True
    assert body["provider_diagnostics_available"] is True


def test_diagnostics_include_supported_modes_and_statuses() -> None:
    body = client.get("/runtime/agent-execution/diagnostics").json()

    assert body["supported_agent_modes"] == [
        "single_turn",
        "tool_enabled",
    ]
    assert body["supported_agent_statuses"] == [
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
    ]


def test_diagnostics_confirm_mock_provider_and_collection_fields() -> None:
    body = client.get("/runtime/agent-execution/diagnostics").json()

    assert body["mock_provider_available"] is True
    assert isinstance(body["warnings"], list)
    assert body["metadata"] == {}


def test_agent_execution_diagnostics_are_deterministic() -> None:
    service = AgentExecutionDiagnosticsService()

    assert service.get_diagnostics() == service.get_diagnostics()
    assert client.get(
        "/runtime/agent-execution/diagnostics"
    ).json() == client.get(
        "/runtime/agent-execution/diagnostics"
    ).json()
