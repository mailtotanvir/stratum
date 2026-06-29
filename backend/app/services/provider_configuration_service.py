from collections.abc import Iterable

from app.models.provider_configuration import (
    OpenAICompatibleProviderConfiguration,
    ProviderConfiguration,
    ProviderConfigurationSnapshot,
)


BUILT_IN_PROVIDER_CONFIGURATIONS = [
    ProviderConfiguration(
        provider_id="anthropic",
        display_name="Anthropic",
        api_style="anthropic",
        base_url="https://api.anthropic.com/v1",
        supports_streaming=True,
        supports_tools=True,
        default_model="claude-sonnet-4.5",
        available_models=["claude-sonnet-4.5"],
    ),
    ProviderConfiguration(
        provider_id="fake",
        display_name="Fake Provider",
        api_style="fake",
        supports_streaming=True,
        default_model="fake-model",
        available_models=["fake-model"],
        enabled=True,
    ),
    ProviderConfiguration(
        provider_id="gemini",
        display_name="Google Gemini",
        api_style="openai-compatible",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    ProviderConfiguration(
        provider_id="groq",
        display_name="Groq",
        api_style="openai-compatible",
        base_url="https://api.groq.com/openai/v1",
    ),
    ProviderConfiguration(
        provider_id="mock",
        display_name="Mock Provider",
        api_style="mock",
        base_url="mock://local",
        supports_streaming=True,
        supports_tools=True,
        default_model="mock-small",
        available_models=["mock-large", "mock-small"],
        enabled=True,
    ),
    ProviderConfiguration(
        provider_id="ollama",
        display_name="Ollama",
        api_style="openai-compatible",
        base_url="http://localhost:11434/v1",
        default_model="local-default",
        available_models=["local-default"],
    ),
    OpenAICompatibleProviderConfiguration(
        provider_id="openai-compatible",
        display_name="OpenAI Compatible",
        api_style="openai-compatible",
        base_url=None,
        default_model=None,
        available_models=[],
    ),
    ProviderConfiguration(
        provider_id="openrouter",
        display_name="OpenRouter",
        api_style="openai-compatible",
        base_url="https://openrouter.ai/api/v1",
        supports_streaming=True,
        supports_tools=True,
        default_model="provider-routed",
        available_models=["provider-routed"],
    ),
    ProviderConfiguration(
        provider_id="siliconflow",
        display_name="SiliconFlow",
        api_style="openai-compatible",
        base_url="https://api.siliconflow.com/v1",
        default_model="qwen3-32b",
        available_models=["qwen3-32b"],
    ),
]


class ProviderConfigurationService:
    def __init__(
        self,
        configurations: Iterable[ProviderConfiguration] | None = None,
    ) -> None:
        self._configurations: dict[str, ProviderConfiguration] = {}
        source = (
            BUILT_IN_PROVIDER_CONFIGURATIONS
            if configurations is None
            else configurations
        )
        for configuration in source:
            self.register(configuration)

    def register(
        self,
        configuration: ProviderConfiguration,
    ) -> None:
        if configuration.provider_id in self._configurations:
            raise ValueError(
                "Provider configuration already registered: "
                f"{configuration.provider_id}"
            )
        self._configurations[configuration.provider_id] = (
            configuration.model_copy(deep=True)
        )

    def list_configurations(self) -> list[ProviderConfiguration]:
        return [
            self._configurations[provider_id].model_copy(deep=True)
            for provider_id in sorted(self._configurations)
        ]

    def get(self, provider_id: str) -> ProviderConfiguration:
        try:
            configuration = self._configurations[provider_id]
        except KeyError as exc:
            raise ValueError(
                f"Provider configuration is not registered: {provider_id}"
            ) from exc
        return configuration.model_copy(deep=True)

    def has(self, provider_id: str) -> bool:
        return provider_id in self._configurations

    def exists(self, provider_id: str) -> bool:
        return self.has(provider_id)

    def enabled(self, provider_id: str) -> bool:
        return self.get(provider_id).enabled

    def default_model(self, provider_id: str) -> str | None:
        return self.get(provider_id).default_model

    def update(
        self,
        configuration: ProviderConfiguration,
    ) -> ProviderConfiguration:
        if not self.has(configuration.provider_id):
            raise ValueError(
                "Provider configuration is not registered: "
                f"{configuration.provider_id}"
            )
        stored = configuration.model_copy(deep=True)
        self._configurations[configuration.provider_id] = stored
        return stored.model_copy(deep=True)

    def snapshot(self) -> ProviderConfigurationSnapshot:
        return ProviderConfigurationSnapshot(
            providers=self.list_configurations(),
            metadata={},
        )


provider_configuration_service = ProviderConfigurationService()
