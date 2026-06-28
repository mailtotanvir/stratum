from app.providers.base_provider import BaseProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_compatible_provider import (
    OPENAI_COMPATIBLE_BASE_URL,
    OPENAI_COMPATIBLE_PROVIDER_NAME,
    OpenAICompatibleProvider,
)


class ProviderRegistry:
    def __init__(
        self,
        providers: list[BaseProvider] | None = None,
    ) -> None:
        self._providers: dict[str, BaseProvider] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: BaseProvider) -> None:
        provider_name = provider.provider_name()
        if provider_name in self._providers:
            raise ValueError(f"Provider already registered: {provider_name}")
        self._providers[provider_name] = provider

    def provider(self, name: str) -> BaseProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {name}") from exc

    def providers(self) -> list[str]:
        return sorted(self._providers)

    def model_exists(
        self,
        provider: str,
        model: str,
    ) -> bool:
        try:
            registered_provider = self.provider(provider)
        except ValueError:
            return False
        return model in registered_provider.supported_models()

    def supported_models(self, provider: str) -> list[str]:
        return sorted(self.provider(provider).supported_models())


provider_registry = ProviderRegistry(
    [
        MockProvider(),
        OpenAICompatibleProvider(
            provider_name=OPENAI_COMPATIBLE_PROVIDER_NAME,
            base_url=OPENAI_COMPATIBLE_BASE_URL,
            api_key="",
        ),
    ]
)
