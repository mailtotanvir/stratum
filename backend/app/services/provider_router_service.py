from app.models.provider_routing import (
    ProviderRoutingDecision,
    ProviderRoutingResult,
)
from app.providers.provider_registry import (
    ProviderRegistry,
    provider_registry,
)
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
    provider_capability_registry_service,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
    provider_configuration_service,
)


PROVIDER_ADAPTER_ALIASES = {
    "groq": "openai-compatible",
    "openrouter": "openai-compatible",
    "siliconflow": "openai-compatible",
}


class ProviderRouterService:
    def __init__(
        self,
        configurations: ProviderConfigurationService | None = None,
        adapters: ProviderRegistry | None = None,
        capabilities: ProviderCapabilityRegistryService | None = None,
    ) -> None:
        self._configurations = (
            configurations or provider_configuration_service
        )
        self._adapters = adapters or provider_registry
        self._capabilities = (
            capabilities or provider_capability_registry_service
        )

    def resolve(
        self,
        provider: str,
        model: str | None = None,
    ) -> ProviderRoutingResult:
        if not self._configurations.exists(provider):
            return _unresolved(
                provider,
                model,
                "Provider configuration is not registered.",
                "unknown_provider_configuration",
            )

        configuration = self._configurations.get(provider)
        if not configuration.enabled:
            return _unresolved(
                provider,
                model,
                "Provider configuration is disabled.",
                "provider_disabled",
            )

        resolved_model = model or configuration.default_model
        if resolved_model is None:
            return _unresolved(
                provider,
                model,
                "Provider model is not configured.",
                "missing_model",
            )

        adapter_provider_name = PROVIDER_ADAPTER_ALIASES.get(
            provider,
            provider,
        )
        try:
            self._adapters.provider(adapter_provider_name)
        except ValueError:
            return _unresolved(
                provider,
                resolved_model,
                "Provider adapter is not registered.",
                "adapter_not_registered",
                adapter_provider_name=adapter_provider_name,
            )

        try:
            descriptor = self._capabilities.get_model(
                provider,
                resolved_model,
            )
        except ValueError:
            return _unresolved(
                provider,
                resolved_model,
                "Provider model is not registered in the capability registry.",
                "unknown_capability_model",
                adapter_provider_name=adapter_provider_name,
            )

        is_alias = adapter_provider_name != provider
        return ProviderRoutingResult(
            resolved=True,
            decision=ProviderRoutingDecision(
                provider_id=provider,
                model=resolved_model,
                reason=(
                    "configured_alias_resolved"
                    if is_alias
                    else "configured_provider_resolved"
                ),
                source="configured",
                adapter_provider_name=adapter_provider_name,
                base_url=configuration.base_url,
                timeout_seconds=configuration.timeout_seconds,
                enabled=configuration.enabled,
                metadata={
                    "alias": is_alias,
                    "capability_status": descriptor.status.value,
                    "capabilities": [
                        capability.value
                        for capability in descriptor.capabilities
                    ],
                },
            ),
            metadata={},
        )


def _unresolved(
    provider: str,
    model: str | None,
    error_message: str,
    error_code: str,
    *,
    adapter_provider_name: str | None = None,
) -> ProviderRoutingResult:
    metadata = {
        "provider": provider,
        "model": model,
        "error_code": error_code,
        "adapter_provider_name": adapter_provider_name,
    }
    return ProviderRoutingResult(
        resolved=False,
        error_message=error_message,
        metadata={
            key: value
            for key, value in metadata.items()
            if value is not None
        },
    )


provider_router_service = ProviderRouterService()
