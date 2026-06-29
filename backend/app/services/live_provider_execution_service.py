from app.services.live_provider_adapter_registry_service import (
    LiveProviderAdapterRegistryService,
)
from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)
from app.services.provider_execution_service import ProviderExecutionService


class LiveProviderExecutionServiceFactory:
    """Assemble ProviderExecutionService for live configured providers.

    This is the production composition boundary:
    environment -> configuration -> live adapter registry -> execution service.
    """

    def create_from_environment(
        self,
        *,
        configuration_service: ProviderConfigurationService | None = None,
        loader: ProviderConfigurationLoaderService | None = None,
    ) -> ProviderExecutionService:
        adapter_registry = (
            LiveProviderAdapterRegistryService.from_environment(
                configuration_service=configuration_service,
                loader=loader,
            ).build_registry()
        )
        return ProviderExecutionService(
            adapter_registry=adapter_registry,
        )


live_provider_execution_service_factory = LiveProviderExecutionServiceFactory()
