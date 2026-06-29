from app.models.provider_capability import (
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.providers.mock_provider import MockProvider
from app.providers.provider_registry import ProviderRegistry
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)
from app.services.provider_router_service import ProviderRouterService


def enabled_configuration(
    service: ProviderConfigurationService,
    provider_name: str,
    *,
    default_model: str | None,
) -> None:
    current = service.get(provider_name)
    service.update(
        current.model_copy(
            update={
                "enabled": True,
                "default_model": default_model,
            },
            deep=True,
        )
    )


def test_mock_resolves_with_default_model() -> None:
    result = ProviderRouterService().resolve("mock")

    assert result.resolved is True
    assert result.error_message is None
    assert result.decision is not None
    assert result.decision.provider == "mock"
    assert result.decision.model == "mock-small"
    assert result.decision.adapter_provider_name == "mock"
    assert result.decision.enabled is True
    assert result.decision.reason == "configured_provider_resolved"


def test_explicit_mock_model_resolves() -> None:
    result = ProviderRouterService().resolve("mock", "mock-large")

    assert result.resolved is True
    assert result.decision is not None
    assert result.decision.model == "mock-large"
    assert result.decision.metadata["capabilities"] == [
        "chat",
        "completion",
        "tool_call",
        "streaming",
    ]


def test_unknown_provider_fails() -> None:
    result = ProviderRouterService().resolve("missing")

    assert result.resolved is False
    assert result.decision is None
    assert result.metadata["error_code"] == (
        "unknown_provider_configuration"
    )


def test_disabled_provider_fails() -> None:
    result = ProviderRouterService().resolve("openrouter")

    assert result.resolved is False
    assert result.metadata["error_code"] == "provider_disabled"


def test_missing_model_without_default_fails() -> None:
    configurations = ProviderConfigurationService()
    enabled_configuration(
        configurations,
        "openai-compatible",
        default_model=None,
    )

    result = ProviderRouterService(
        configurations=configurations
    ).resolve("openai-compatible")

    assert result.resolved is False
    assert result.metadata["error_code"] == "missing_model"


def test_unregistered_adapter_fails() -> None:
    configurations = ProviderConfigurationService()
    enabled_configuration(
        configurations,
        "anthropic",
        default_model="claude-sonnet-4.5",
    )
    service = ProviderRouterService(
        configurations=configurations,
        adapters=ProviderRegistry([MockProvider()]),
    )

    result = service.resolve("anthropic")

    assert result.resolved is False
    assert result.metadata["error_code"] == "adapter_not_registered"
    assert result.metadata["adapter_provider_name"] == "anthropic"


def test_unknown_capability_model_fails() -> None:
    result = ProviderRouterService().resolve("mock", "missing-model")

    assert result.resolved is False
    assert result.metadata["error_code"] == "unknown_capability_model"


def test_alias_resolves_to_openai_compatible_adapter() -> None:
    configurations = ProviderConfigurationService()
    enabled_configuration(
        configurations,
        "openrouter",
        default_model="provider-routed",
    )

    result = ProviderRouterService(
        configurations=configurations
    ).resolve("openrouter")

    assert result.resolved is True
    assert result.decision is not None
    assert result.decision.provider == "openrouter"
    assert result.decision.model == "provider-routed"
    assert result.decision.adapter_provider_name == "openai-compatible"
    assert result.decision.reason == "configured_alias_resolved"
    assert result.decision.base_url == "https://openrouter.ai/api/v1"
    assert result.decision.metadata["alias"] is True


def test_test_local_alias_capability_can_resolve() -> None:
    configurations = ProviderConfigurationService()
    enabled_configuration(
        configurations,
        "groq",
        default_model="groq-test-model",
    )
    capabilities = ProviderCapabilityRegistryService(
        [
            ProviderModelDescriptor(
                provider="groq",
                model="groq-test-model",
                capabilities=[ProviderModelCapability.CHAT],
            )
        ]
    )

    result = ProviderRouterService(
        configurations=configurations,
        capabilities=capabilities,
    ).resolve("groq")

    assert result.resolved is True
    assert result.decision is not None
    assert result.decision.adapter_provider_name == "openai-compatible"


def test_routing_result_is_deterministic() -> None:
    service = ProviderRouterService()

    first = service.resolve("mock")
    second = service.resolve("mock")

    assert first == second
