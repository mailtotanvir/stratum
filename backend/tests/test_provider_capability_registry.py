import pytest
from pydantic import ValidationError

from app.models.provider_capability import (
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
)


EXPECTED_PROVIDERS = [
    "anthropic",
    "mock",
    "ollama",
    "openai",
    "openrouter",
    "siliconflow",
]


def test_built_in_snapshot_includes_expected_providers() -> None:
    snapshot = ProviderCapabilityRegistryService().snapshot()

    assert snapshot.providers == EXPECTED_PROVIDERS
    assert {
        (model.provider, model.model)
        for model in snapshot.models
    } == {
        ("openai", "gpt-5.5"),
        ("anthropic", "claude-sonnet-4.5"),
        ("mock", "mock-large"),
        ("mock", "mock-small"),
        ("openrouter", "provider-routed"),
        ("siliconflow", "qwen3-32b"),
        ("ollama", "local-default"),
    }
    assert snapshot.metadata == {
        "source": "built_in_provider_capability_registry",
        "model_count": 7,
    }


def test_model_descriptor_validation() -> None:
    descriptor = ProviderModelDescriptor(
        provider="test-provider",
        model="test-model",
        capabilities=[ProviderModelCapability.CHAT],
        context_window=1024,
        max_output_tokens=256,
        cost_per_1k_input_tokens=0,
        cost_per_1k_output_tokens=0.01,
    )

    assert descriptor.provider == "test-provider"
    assert descriptor.model == "test-model"
    assert descriptor.currency == "USD"


def test_empty_capabilities_invalid() -> None:
    with pytest.raises(ValidationError):
        ProviderModelDescriptor(
            provider="test-provider",
            model="test-model",
            capabilities=[],
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "", "model": "test-model"},
        {"provider": "   ", "model": "test-model"},
        {"provider": "test-provider", "model": ""},
        {"provider": "test-provider", "model": "   "},
        {"provider": "test-provider", "model": "test-model", "context_window": 0},
        {
            "provider": "test-provider",
            "model": "test-model",
            "max_output_tokens": 0,
        },
        {
            "provider": "test-provider",
            "model": "test-model",
            "cost_per_1k_input_tokens": -0.01,
        },
        {
            "provider": "test-provider",
            "model": "test-model",
            "cost_per_1k_output_tokens": -0.01,
        },
    ],
)
def test_model_descriptor_rejects_invalid_fields(payload) -> None:
    with pytest.raises(ValidationError):
        ProviderModelDescriptor(
            capabilities=[ProviderModelCapability.CHAT],
            **payload,
        )


def test_lookup_known_model() -> None:
    model = ProviderCapabilityRegistryService().get_model(
        "openai",
        "gpt-5.5",
    )

    assert model.provider == "openai"
    assert model.model == "gpt-5.5"


def test_lookup_unknown_model_raises() -> None:
    with pytest.raises(
        ValueError,
        match="Unknown provider model: missing/model",
    ):
        ProviderCapabilityRegistryService().get_model("missing", "model")


def test_supports_returns_true_for_supported_capability() -> None:
    assert ProviderCapabilityRegistryService().supports(
        "openai",
        "gpt-5.5",
        ProviderModelCapability.CHAT,
    )


def test_supports_returns_false_for_unsupported_capability() -> None:
    assert not ProviderCapabilityRegistryService().supports(
        "ollama",
        "local-default",
        ProviderModelCapability.TOOL_CALL,
    )


def test_supports_returns_false_for_unknown_model() -> None:
    assert not ProviderCapabilityRegistryService().supports(
        "missing",
        "model",
        ProviderModelCapability.CHAT,
    )


def test_snapshot_is_deterministic_in_ordering() -> None:
    service = ProviderCapabilityRegistryService()

    first = service.snapshot().model_dump(mode="json")
    second = service.snapshot().model_dump(mode="json")

    assert first == second
    assert [
        (model["provider"], model["model"])
        for model in first["models"]
    ] == [
        ("anthropic", "claude-sonnet-4.5"),
        ("mock", "mock-large"),
        ("mock", "mock-small"),
        ("ollama", "local-default"),
        ("openai", "gpt-5.5"),
        ("openrouter", "provider-routed"),
        ("siliconflow", "qwen3-32b"),
    ]
