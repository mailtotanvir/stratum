from fastapi.testclient import TestClient

from app.main import app
from app.services.provider_execution_diagnostics_service import (
    ProviderExecutionDiagnosticsService,
)


client = TestClient(app)


def test_provider_execution_diagnostics_route_returns_200() -> None:
    response = client.get("/runtime/provider-execution/diagnostics")

    assert response.status_code == 200


def test_diagnostics_include_mock_adapter_and_models() -> None:
    body = client.get("/runtime/provider-execution/diagnostics").json()

    assert "mock" in body["registered_provider_adapters"]
    assert body["supported_adapter_models"]["mock"] == [
        "mock-large",
        "mock-small",
    ]
    assert body["mock_provider_available"] is True
    assert body["mock_capability_descriptors_exist"] is True


def test_diagnostics_include_capability_registry_providers() -> None:
    body = client.get("/runtime/provider-execution/diagnostics").json()

    assert body["capability_registry_providers"] == [
        "anthropic",
        "mock",
        "ollama",
        "openai",
        "openrouter",
        "siliconflow",
    ]
    models = [
        (descriptor["provider"], descriptor["model"])
        for descriptor in body["capability_registry_models"]
    ]
    assert ("mock", "mock-small") in models
    assert ("mock", "mock-large") in models


def test_diagnostics_confirm_services_are_ready() -> None:
    body = client.get("/runtime/provider-execution/diagnostics").json()

    assert body["validator_status"] == "ready"
    assert body["execution_service_status"] == "ready"
    assert isinstance(body["warnings"], list)


def test_diagnostics_are_deterministic() -> None:
    service = ProviderExecutionDiagnosticsService()

    first = service.get_diagnostics()
    second = service.get_diagnostics()

    assert first == second
    assert client.get(
        "/runtime/provider-execution/diagnostics"
    ).json() == client.get(
        "/runtime/provider-execution/diagnostics"
    ).json()
