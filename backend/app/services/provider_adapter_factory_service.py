from app.models.provider_configuration import ProviderConfiguration
from app.providers.base import ProviderAdapter
from app.providers.configured_transport import ConfiguredTransport
from app.providers.httpx_transport import HttpxTransport
from app.providers.openai_compatible import OpenAICompatibleProviderAdapter
from app.providers.transport import Transport
from app.services.provider_authentication_service import (
    ProviderAuthenticationService,
    provider_authentication_service,
)
from app.services.provider_configuration_validator_service import (
    ProviderConfigurationValidatorService,
    provider_configuration_validator_service,
)


class ProviderAdapterFactoryService:
    """Build concrete provider adapters from configuration."""

    def __init__(
        self,
        *,
        authentication: ProviderAuthenticationService | None = None,
        validator: ProviderConfigurationValidatorService | None = None,
    ) -> None:
        self._authentication = (
            authentication or provider_authentication_service
        )
        self._validator = validator or provider_configuration_validator_service

    def create(
        self,
        configuration: ProviderConfiguration,
        *,
        transport: Transport | None = None,
    ) -> ProviderAdapter:
        self._validator.validate_for_live_execution(configuration)

        headers = {
            "Content-Type": "application/json",
            **configuration.default_headers,
            **self._authentication.headers_for(configuration),
        }

        configured_transport = ConfiguredTransport(
            transport=transport
            or HttpxTransport(timeout_seconds=configuration.timeout_seconds),
            base_url=configuration.base_url,
            default_headers=headers,
        )

        return OpenAICompatibleProviderAdapter(
            provider_id=configuration.provider_id,
            chat_completions_path=_chat_completions_path(configuration),
            transport=configured_transport,
        )


def _chat_completions_path(
    configuration: ProviderConfiguration,
) -> str:
    value = configuration.metadata.get("chat_completions_path")
    if value is None:
        return "chat/completions"
    stripped = str(value).strip()
    return stripped or "chat/completions"


provider_adapter_factory_service = ProviderAdapterFactoryService()
