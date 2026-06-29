import pytest

from app.providers.mock_provider import MockProvider
from app.providers.provider_registry import ProviderRegistry, provider_registry


def test_default_registry_contains_mock_provider() -> None:
    assert provider_registry.providers() == [
        "mock",
        "openai-compatible",
    ]


def test_duplicate_registration_rejected() -> None:
    registry = ProviderRegistry([MockProvider()])

    with pytest.raises(
        ValueError,
        match="Provider already registered: mock",
    ):
        registry.register(MockProvider())


def test_lookup_known_provider() -> None:
    provider = provider_registry.provider("mock")

    assert provider.provider_name() == "mock"


def test_lookup_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown provider: missing"):
        provider_registry.provider("missing")


def test_supported_models() -> None:
    assert provider_registry.supported_models("mock") == [
        "mock-large",
        "mock-small",
    ]


def test_model_exists_true() -> None:
    assert provider_registry.model_exists("mock", "mock-small") is True


def test_model_exists_false() -> None:
    assert provider_registry.model_exists("mock", "missing") is False
    assert provider_registry.model_exists("missing", "mock-small") is False


def test_providers_list_deterministic() -> None:
    first = provider_registry.providers()
    second = provider_registry.providers()

    assert first == second == [
        "mock",
        "openai-compatible",
    ]
