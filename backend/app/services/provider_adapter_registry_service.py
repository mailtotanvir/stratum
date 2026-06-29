from collections.abc import Iterable

from app.providers.base import ProviderAdapter
from app.providers.fake import FakeProviderAdapter
from app.providers.openai_compatible import OpenAICompatibleProviderAdapter


class ProviderAdapterRegistryService:
    def __init__(
        self,
        adapters: Iterable[ProviderAdapter] | None = None,
    ) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}
        source = (
            [
                FakeProviderAdapter(),
                OpenAICompatibleProviderAdapter(),
            ]
            if adapters is None
            else adapters
        )
        for adapter in source:
            self._register(adapter)

    def list_adapters(self) -> list[ProviderAdapter]:
        return [
            self._adapters[provider_id]
            for provider_id in sorted(self._adapters)
        ]

    def get_adapter(self, provider_id: str) -> ProviderAdapter:
        try:
            return self._adapters[provider_id]
        except KeyError as exc:
            raise ValueError(
                f"Provider adapter is not registered: {provider_id}"
            ) from exc

    def has_adapter(self, provider_id: str) -> bool:
        return provider_id in self._adapters

    def register(self, adapter: ProviderAdapter) -> None:
        self._register(adapter)

    def _register(self, adapter: ProviderAdapter) -> None:
        provider_id = adapter.provider_id
        if provider_id in self._adapters:
            raise ValueError(
                f"Provider adapter already registered: {provider_id}"
            )
        self._adapters[provider_id] = adapter


provider_adapter_registry_service = ProviderAdapterRegistryService()
