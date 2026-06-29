import os
from collections.abc import Mapping

from app.models.provider_configuration import ProviderConfiguration
from app.services.provider_configuration_service import ProviderConfigurationService


class ProviderConfigurationLoaderService:
    def __init__(
        self,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._environment = environment

    @property
    def environment(self) -> Mapping[str, str]:
        return os.environ if self._environment is None else self._environment

    def load_from_environment(
        self,
        service: ProviderConfigurationService,
    ) -> ProviderConfiguration | None:
        provider_id = self._read("STRATUM_PROVIDER_ID")
        if provider_id is None:
            return None

        display_name = (
            self._read("STRATUM_PROVIDER_DISPLAY_NAME")
            or provider_id
        )
        base_url = self._read("STRATUM_PROVIDER_BASE_URL")
        api_key = self._read("STRATUM_PROVIDER_API_KEY")
        model = self._read("STRATUM_PROVIDER_MODEL")
        enabled = self._read_bool("STRATUM_PROVIDER_ENABLED", default=False)

        existing = service.get(provider_id) if service.has(provider_id) else None

        configuration = ProviderConfiguration(
            provider_id=provider_id,
            display_name=display_name,
            api_style=(
                existing.api_style
                if existing is not None
                else "openai-compatible"
            ),
            base_url=base_url if base_url is not None else (
                existing.base_url if existing is not None else None
            ),
            supports_streaming=(
                existing.supports_streaming
                if existing is not None
                else True
            ),
            supports_tools=(
                existing.supports_tools
                if existing is not None
                else False
            ),
            supports_json_mode=(
                existing.supports_json_mode
                if existing is not None
                else False
            ),
            supports_reasoning=(
                existing.supports_reasoning
                if existing is not None
                else False
            ),
            supports_vision=(
                existing.supports_vision
                if existing is not None
                else False
            ),
            supports_embeddings=(
                existing.supports_embeddings
                if existing is not None
                else False
            ),
            supports_audio=(
                existing.supports_audio
                if existing is not None
                else False
            ),
            default_model=model if model is not None else (
                existing.default_model if existing is not None else None
            ),
            available_models=(
                [model]
                if model is not None
                else (
                    existing.available_models
                    if existing is not None
                    else []
                )
            ),
            enabled=enabled,
            timeout_seconds=(
                existing.timeout_seconds
                if existing is not None
                else 120
            ),
            default_headers=(
                existing.default_headers
                if existing is not None
                else {}
            ),
            metadata={
                **(existing.metadata if existing is not None else {}),
                "configuration_source": "environment",
                **({"api_key": api_key} if api_key is not None else {}),
            },
        )

        if service.has(provider_id):
            return service.update(configuration)

        service.register(configuration)
        return service.get(provider_id)

    def _read(self, key: str) -> str | None:
        value = self.environment.get(key)
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _read_bool(self, key: str, *, default: bool) -> bool:
        value = self._read(key)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "on", "enabled"}
