from collections.abc import Iterable

from app.models.provider_configuration import ProviderConfiguration
from app.providers.base import ProviderAdapter
from app.providers.fake import FakeProviderAdapter
from app.services.provider_adapter_factory_service import (
    ProviderAdapterFactoryService,
    provider_adapter_factory_service,
)
from app.services.provider_adapter_registry_service import (
    ProviderAdapterRegistryService,
)
from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)


class LiveProviderAdapterRegistryService:
    """Build adapter registries from provider configuration.

    This keeps live provider assembly out of ProviderExecutionService.
    """

    def __init__(
        self,
        *,
        configuration_service: ProviderConfigurationService,
        factory: ProviderAdapterFactoryService | None = None,
    ) -> None:
        self._configuration_service = configuration_service
        self._factory = factory or provider_adapter_factory_service

    @classmethod
    def from_environment(
        cls,
        *,
        configuration_service: ProviderConfigurationService | None = None,
        loader: ProviderConfigurationLoaderService | None = None,
        factory: ProviderAdapterFactoryService | None = None,
    ) -> "LiveProviderAdapterRegistryService":
        service = configuration_service or ProviderConfigurationService()
        (loader or ProviderConfigurationLoaderService()).load_from_environment(
            service
        )
        return cls(
            configuration_service=service,
            factory=factory,
        )

    def build_registry(
        self,
        *,
        base_adapters: Iterable[ProviderAdapter] | None = None,
    ) -> ProviderAdapterRegistryService:
        registry = ProviderAdapterRegistryService(
            list(base_adapters)
            if base_adapters is not None
            else [FakeProviderAdapter()]
        )

        for configuration in self._configuration_service.list_configurations():
            if not _should_register_live_adapter(configuration):
                continue
            registry.register(self._factory.create(configuration))

        return registry


def _should_register_live_adapter(
    configuration: ProviderConfiguration,
) -> bool:
    return (
        configuration.enabled
        and configuration.api_style == "openai-compatible"
        and configuration.base_url is not None
    )
