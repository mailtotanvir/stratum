from app.models.provider_live_diagnostics import ProviderLiveDiagnostics
from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)
from app.services.provider_configuration_validator_service import (
    ProviderConfigurationError,
    ProviderConfigurationValidatorService,
    provider_configuration_validator_service,
)


class ProviderLiveDiagnosticsService:
    def __init__(
        self,
        *,
        loader: ProviderConfigurationLoaderService | None = None,
        validator: ProviderConfigurationValidatorService | None = None,
    ) -> None:
        self._loader = loader or ProviderConfigurationLoaderService()
        self._validator = validator or provider_configuration_validator_service

    def inspect_environment(self) -> ProviderLiveDiagnostics:
        service = ProviderConfigurationService([])
        configuration = self._loader.load_from_environment(service)

        if configuration is None:
            return ProviderLiveDiagnostics(
                configured=False,
                ready=False,
                issues=["No live provider environment configuration found."],
            )

        issues: list[str] = []
        try:
            self._validator.validate_for_live_execution(configuration)
            ready = True
        except ProviderConfigurationError as exc:
            ready = False
            issues.append(str(exc))

        return ProviderLiveDiagnostics(
            configured=True,
            ready=ready,
            provider_id=configuration.provider_id,
            display_name=configuration.display_name,
            api_style=configuration.api_style,
            base_url=configuration.base_url,
            default_model=configuration.default_model,
            enabled=configuration.enabled,
            supports_streaming=configuration.supports_streaming,
            has_api_key=bool(
                str(configuration.metadata.get("api_key", "")).strip()
            ),
            issues=issues,
            metadata={
                "configuration_source": configuration.metadata.get(
                    "configuration_source"
                ),
                "chat_completions_path": configuration.metadata.get(
                    "chat_completions_path",
                    "chat/completions",
                ),
            },
        )


provider_live_diagnostics_service = ProviderLiveDiagnosticsService()
