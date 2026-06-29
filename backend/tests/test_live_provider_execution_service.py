import asyncio

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
)
from app.services.live_provider_execution_service import (
    LiveProviderExecutionServiceFactory,
)
from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)


def request(provider: str, model: str) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model=model,
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Hello.",
            )
        ],
    )


def test_factory_without_environment_preserves_fake_execution_path() -> None:
    service = LiveProviderExecutionServiceFactory().create_from_environment(
        configuration_service=ProviderConfigurationService([]),
        loader=ProviderConfigurationLoaderService({}),
    )

    result = asyncio.run(service.complete(request("fake", "fake-model")))

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.provider == "fake"
    assert result.model == "fake-model"


def test_factory_loads_environment_provider_into_execution_service() -> None:
    service = LiveProviderExecutionServiceFactory().create_from_environment(
        configuration_service=ProviderConfigurationService([]),
        loader=ProviderConfigurationLoaderService(
            {
                "STRATUM_PROVIDER_ID": "env-live",
                "STRATUM_PROVIDER_BASE_URL": "https://example.test/v1",
                "STRATUM_PROVIDER_API_KEY": "secret-key",
                "STRATUM_PROVIDER_MODEL": "env-model",
                "STRATUM_PROVIDER_ENABLED": "true",
            }
        ),
    )

    assert service._adapter_registry.has_adapter("env-live") is True
    assert service._adapter_registry.has_adapter("fake") is True


def test_factory_does_not_register_disabled_environment_provider() -> None:
    service = LiveProviderExecutionServiceFactory().create_from_environment(
        configuration_service=ProviderConfigurationService([]),
        loader=ProviderConfigurationLoaderService(
            {
                "STRATUM_PROVIDER_ID": "env-live",
                "STRATUM_PROVIDER_BASE_URL": "https://example.test/v1",
                "STRATUM_PROVIDER_MODEL": "env-model",
                "STRATUM_PROVIDER_ENABLED": "false",
            }
        ),
    )

    assert service._adapter_registry.has_adapter("env-live") is False
    assert service._adapter_registry.has_adapter("fake") is True
