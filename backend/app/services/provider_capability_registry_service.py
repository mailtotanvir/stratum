from collections.abc import Iterable

from app.models.provider_capability import (
    ProviderModelCapability,
    ProviderModelDescriptor,
    ProviderRegistrySnapshot,
)


BUILT_IN_PROVIDER_MODELS = [
    ProviderModelDescriptor(
        provider="anthropic",
        model="claude-sonnet-4.5",
        display_name="Claude Sonnet 4.5",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.TOOL_CALL,
            ProviderModelCapability.STREAMING,
            ProviderModelCapability.JSON_OUTPUT,
        ],
        context_window=200000,
        max_output_tokens=8192,
    ),
    ProviderModelDescriptor(
        provider="mock",
        model="mock-large",
        display_name="Mock Large",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.COMPLETION,
            ProviderModelCapability.TOOL_CALL,
            ProviderModelCapability.STREAMING,
        ],
    ),
    ProviderModelDescriptor(
        provider="mock",
        model="mock-small",
        display_name="Mock Small",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.COMPLETION,
            ProviderModelCapability.TOOL_CALL,
        ],
    ),
    ProviderModelDescriptor(
        provider="ollama",
        model="local-default",
        display_name="Local Default",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.COMPLETION,
        ],
    ),
    ProviderModelDescriptor(
        provider="openai",
        model="gpt-5.5",
        display_name="GPT-5.5",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.TOOL_CALL,
            ProviderModelCapability.STREAMING,
            ProviderModelCapability.JSON_OUTPUT,
        ],
        context_window=400000,
        max_output_tokens=128000,
    ),
    ProviderModelDescriptor(
        provider="openrouter",
        model="provider-routed",
        display_name="Provider Routed",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.COMPLETION,
            ProviderModelCapability.TOOL_CALL,
            ProviderModelCapability.STREAMING,
        ],
    ),
    ProviderModelDescriptor(
        provider="siliconflow",
        model="qwen3-32b",
        display_name="Qwen3 32B",
        capabilities=[
            ProviderModelCapability.CHAT,
            ProviderModelCapability.COMPLETION,
        ],
        context_window=32768,
        max_output_tokens=8192,
    ),
]


class ProviderCapabilityRegistryService:
    def __init__(
        self,
        models: Iterable[ProviderModelDescriptor] | None = None,
    ) -> None:
        self._models = _sort_models(models or BUILT_IN_PROVIDER_MODELS)

    def list_models(self) -> list[ProviderModelDescriptor]:
        return [model.model_copy(deep=True) for model in self._models]

    def list_providers(self) -> list[str]:
        return sorted({model.provider for model in self._models})

    def get_model(
        self,
        provider: str,
        model: str,
    ) -> ProviderModelDescriptor:
        for descriptor in self._models:
            if descriptor.provider == provider and descriptor.model == model:
                return descriptor.model_copy(deep=True)
        raise ValueError(f"Unknown provider model: {provider}/{model}")

    def supports(
        self,
        provider: str,
        model: str,
        capability: ProviderModelCapability,
    ) -> bool:
        try:
            descriptor = self.get_model(provider, model)
        except ValueError:
            return False
        return capability in descriptor.capabilities

    def snapshot(self) -> ProviderRegistrySnapshot:
        return ProviderRegistrySnapshot(
            providers=self.list_providers(),
            models=self.list_models(),
            metadata={
                "source": "built_in_provider_capability_registry",
                "model_count": len(self._models),
            },
        )


def _sort_models(
    models: Iterable[ProviderModelDescriptor],
) -> list[ProviderModelDescriptor]:
    return sorted(
        [model.model_copy(deep=True) for model in models],
        key=lambda model: (model.provider, model.model),
    )


provider_capability_registry_service = ProviderCapabilityRegistryService()
