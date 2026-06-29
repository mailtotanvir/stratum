from app.models.provider_configuration import ProviderConfiguration


class ProviderConfigurationError(ValueError):
    pass


class ProviderConfigurationValidatorService:
    def validate_for_live_execution(
        self,
        configuration: ProviderConfiguration,
    ) -> None:
        if not configuration.enabled:
            raise ProviderConfigurationError(
                "Provider is not enabled for live execution: "
                f"{configuration.provider_id}"
            )
        if configuration.api_style != "openai-compatible":
            raise ProviderConfigurationError(
                "Unsupported provider api_style for live execution: "
                f"{configuration.api_style}"
            )
        if configuration.base_url is None or not configuration.base_url.strip():
            raise ProviderConfigurationError(
                "Missing required provider configuration: base_url"
            )
        if configuration.default_model is None or not configuration.default_model.strip():
            raise ProviderConfigurationError(
                "Missing required provider configuration: default_model"
            )
        api_key = configuration.metadata.get("api_key")
        if api_key is None or not str(api_key).strip():
            raise ProviderConfigurationError(
                "Missing required provider configuration: api_key"
            )


provider_configuration_validator_service = (
    ProviderConfigurationValidatorService()
)
