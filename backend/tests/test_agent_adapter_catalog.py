from fastapi.testclient import TestClient

from app.main import app
from app.models.agent_adapter import AgentCapabilityManifest
from app.services.agent_adapter_catalog_service import (
    AgentAdapterCatalogService,
)
from app.services.agent_adapter_registry_service import (
    AgentAdapterRegistryService,
)


client = TestClient(app)


def test_list_agent_adapters_route_returns_built_in_catalog() -> None:
    response = client.get("/agent-adapters")

    assert response.status_code == 200
    body = response.json()
    assert [entry["manifest"]["adapter_id"] for entry in body["adapters"]] == [
        "agent-example",
        "agent-fake",
        "agent-mock-external",
    ]


def test_get_agent_adapter_manifest_route_returns_single_manifest() -> None:
    response = client.get("/agent-adapters/agent-fake")

    assert response.status_code == 200
    assert response.json()["display_name"] == "Fake Agent"


def test_get_agent_adapter_manifest_route_returns_404_for_unknown_adapter() -> None:
    response = client.get("/agent-adapters/missing")

    assert response.status_code == 404


def test_agent_event_normalization_catalog_route_returns_supported_values() -> None:
    body = client.get("/agent-adapters/normalization").json()

    assert "started" in body["source_event_kinds"]
    assert "completed" in body["source_event_kinds"]
    assert "healthy" not in body["severities"]
    assert body["runtime_event_types"]


def test_agent_adapter_registry_diagnostics_route_is_healthy_for_built_ins() -> None:
    body = client.get("/agent-adapters/diagnostics").json()

    assert body["status"] == "healthy"
    assert body["total_registered"] == 3
    assert body["duplicate_adapter_ids"] == []
    assert body["invalid_adapter_ids"] == []


def test_catalog_service_marks_invalid_definitions() -> None:
    registry = AgentAdapterRegistryService(
        [
            type(
                "Adapter",
                (),
                {
                    "adapter_id": "agent-invalid",
                    "manifest": AgentCapabilityManifest(
                        adapter_id="agent-invalid",
                        display_name="Invalid Agent",
                    ),
                },
            )()
        ]
    )
    service = AgentAdapterCatalogService(registry=registry)

    diagnostics = service.diagnostics()

    assert diagnostics.status == "degraded"
    assert diagnostics.invalid_adapter_ids == ["agent-invalid"]


def test_catalog_service_marks_duplicate_definitions_from_registry_snapshot() -> None:
    class DuplicateRegistry:
        def list_adapters(self):
            return []

        def list_manifests(self):
            return [
                AgentCapabilityManifest(
                    adapter_id="agent-duplicate",
                    display_name="Duplicate Agent",
                    supported_agent_types=["coding"],
                ),
                AgentCapabilityManifest(
                    adapter_id="agent-duplicate",
                    display_name="Duplicate Agent",
                    supported_agent_types=["coding"],
                ),
            ]

    service = AgentAdapterCatalogService(registry=DuplicateRegistry())

    diagnostics = service.diagnostics()

    assert diagnostics.status == "degraded"
    assert diagnostics.duplicate_adapter_ids == ["agent-duplicate"]


def test_catalog_service_uses_deterministic_builtin_definitions() -> None:
    service = AgentAdapterCatalogService()
    adapters = service.list_adapters().adapters

    assert [entry.manifest.adapter_id for entry in adapters] == [
        "agent-example",
        "agent-fake",
        "agent-mock-external",
    ]
    mock_manifest = next(
        entry.manifest
        for entry in adapters
        if entry.manifest.adapter_id == "agent-mock-external"
    )
    assert mock_manifest.description and "demo-only" in mock_manifest.description
    assert mock_manifest.metadata["demo_only"] is True
