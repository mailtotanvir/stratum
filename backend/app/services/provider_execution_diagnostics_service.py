from app.models.provider_execution_diagnostics import (
    ProviderExecutionDiagnostics,
)
from app.providers.provider_registry import (
    ProviderRegistry,
    provider_registry,
)
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
    provider_capability_registry_service,
)
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service,
)
from app.services.provider_execution_validator_service import (
    ProviderExecutionValidatorService,
    provider_execution_validator_service,
)


class ProviderExecutionDiagnosticsService:
    def __init__(
        self,
        adapter_registry: ProviderRegistry | None = None,
        capability_registry: ProviderCapabilityRegistryService | None = None,
        validator: ProviderExecutionValidatorService | None = None,
        execution_service: ProviderExecutionService | None = None,
    ) -> None:
        self._adapter_registry = adapter_registry or provider_registry
        self._capability_registry = (
            capability_registry or provider_capability_registry_service
        )
        self._validator = validator or provider_execution_validator_service
        self._execution_service = (
            execution_service or provider_execution_service
        )

    def get_diagnostics(self) -> ProviderExecutionDiagnostics:
        adapters = self._adapter_registry.providers()
        adapter_models = {
            provider: self._adapter_registry.supported_models(provider)
            for provider in adapters
        }
        capability_snapshot = self._capability_registry.snapshot()
        mock_models = {
            descriptor.model
            for descriptor in capability_snapshot.models
            if descriptor.provider == "mock"
        }

        return ProviderExecutionDiagnostics(
            registered_provider_adapters=adapters,
            supported_adapter_models=adapter_models,
            capability_registry_providers=capability_snapshot.providers,
            capability_registry_models=capability_snapshot.models,
            mock_provider_available="mock" in adapters,
            mock_capability_descriptors_exist={
                "mock-small",
                "mock-large",
            }.issubset(mock_models),
            validator_status=(
                "ready"
                if callable(getattr(self._validator, "validate_request", None))
                else "unavailable"
            ),
            execution_service_status=(
                "ready"
                if callable(getattr(self._execution_service, "execute", None))
                else "unavailable"
            ),
            warnings=[],
        )


provider_execution_diagnostics_service = (
    ProviderExecutionDiagnosticsService()
)
