from app.main import app
from app.models.execution_participant import ExecutionCapabilityRouteRequest
from app.services.execution_participant_registry_service import (
    execution_participant_registry_service,
)

def test_execution_participant_diagnostics_expose_manifest_and_policy() -> None:
    diagnostics = execution_participant_registry_service.diagnostics()

    assert diagnostics.routing_policy == "deterministic-human-governed"
    assert diagnostics.total_participants >= 1
    assert "participant" in diagnostics.registry_views
    assert diagnostics.capabilities["approval"] >= 1


def test_execution_participant_capabilities_are_sorted() -> None:
    capabilities = execution_participant_registry_service.list_capability_manifests()

    assert capabilities == sorted(
        capabilities,
        key=lambda manifest: (manifest.route_order, manifest.participant_id, manifest.capability_id),
    )
    assert any(manifest.capability_id == "approval" for manifest in capabilities)


def test_execution_participant_route_prefers_human_operator_for_approval() -> None:
    route = execution_participant_registry_service.route_capability(
        ExecutionCapabilityRouteRequest(capability_id="approval")
    )

    assert route.selected_participant_id == "human-operator"
    assert route.eligible_participant_ids[0] == "human-operator"


def test_execution_invocation_state_transitions_emit_consistent_events() -> None:
    invocation = execution_participant_registry_service.create_invocation("approval")
    execution_participant_registry_service.start_invocation(invocation.invocation_id)
    completed = execution_participant_registry_service.complete_invocation(
        invocation.invocation_id,
        output_payload={"result": "approved"},
    )

    assert invocation.events[:2] == ["invocation_validated", "invocation_queued"]
    assert completed.state.value == "completed"
    assert completed.events[-2:] == ["invocation_started", "invocation_completed"]
    assert completed.output_payload == {"result": "approved"}
