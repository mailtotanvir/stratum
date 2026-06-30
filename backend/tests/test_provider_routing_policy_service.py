from app.models.provider_routing import ProviderRoutingRequest
from app.services.provider_routing_policy_service import (
    ProviderRoutingPolicyService,
)


def test_explicit_provider_model_wins() -> None:
    decision = ProviderRoutingPolicyService().resolve(
        ProviderRoutingRequest(
            requested_provider_id="mock",
            requested_model="mock-large",
            task_type="analysis",
            budget_mode="premium",
        )
    )

    assert decision.provider_id == "mock"
    assert decision.model == "mock-large"
    assert decision.reason == "explicit_request"
    assert decision.source == "explicit_request"


def test_default_fallback_works() -> None:
    decision = ProviderRoutingPolicyService().resolve(
        ProviderRoutingRequest()
    )

    assert decision.provider_id == "fake"
    assert decision.model == "fake-model"
    assert decision.source == "default_configuration"


def test_unsupported_budget_and_task_fall_back_to_defaults() -> None:
    decision = ProviderRoutingPolicyService().resolve(
        ProviderRoutingRequest(
            task_type="unsupported-task",
            budget_mode="unknown-budget",
        )
    )

    assert decision.provider_id == "fake"
    assert decision.model == "fake-model"
    assert decision.source == "default_configuration"
