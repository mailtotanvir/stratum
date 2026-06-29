import pytest
from pydantic import ValidationError

from app.models.provider_configuration import (
    OpenAICompatibleProviderConfiguration,
    ProviderConfiguration,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)


def configuration(provider_id: str) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider_id=provider_id,
        display_name=provider_id.title(),
        api_style="test",
        base_url=None,
        supports_streaming=False,
        supports_tools=False,
        supports_json_mode=False,
        supports_reasoning=False,
        supports_vision=False,
        supports_embeddings=False,
        supports_audio=False,
        default_model=None,
        available_models=[],
    )


def test_fake_configuration_exists() -> None:
    service = ProviderConfigurationService()

    fake = service.get("fake")

    assert fake.provider_id == "fake"
    assert fake.api_style == "fake"
    assert fake.default_model == "fake-model"
    assert fake.available_models == ["fake-model"]
    assert fake.supports_streaming is True


def test_openai_compatible_configuration_exists_unconfigured() -> None:
    service = ProviderConfigurationService()

    configured = service.get("openai-compatible")

    assert isinstance(
        configured,
        OpenAICompatibleProviderConfiguration,
    )
    assert configured.provider_id == "openai-compatible"
    assert configured.api_style == "openai-compatible"
    assert configured.base_url is None
    assert configured.default_model is None
    assert configured.available_models == []


def test_configuration_ordering_is_deterministic() -> None:
    service = ProviderConfigurationService()

    first = [
        item.provider_id
        for item in service.list_configurations()
    ]
    second = [
        item.provider_id
        for item in service.list_configurations()
    ]

    assert first == second == sorted(first)
    assert "fake" in first
    assert "openai-compatible" in first


def test_get_returns_requested_configuration() -> None:
    service = ProviderConfigurationService()

    first = service.get("fake")
    second = service.get("fake")

    assert first == second
    assert first is not second


def test_has_reports_known_and_unknown_providers() -> None:
    service = ProviderConfigurationService()

    assert service.has("fake") is True
    assert service.has("openai-compatible") is True
    assert service.has("missing") is False


def test_duplicate_registration_is_rejected() -> None:
    duplicate = configuration("duplicate")

    with pytest.raises(
        ValueError,
        match="Provider configuration already registered: duplicate",
    ):
        ProviderConfigurationService([duplicate, duplicate])


def test_unknown_provider_raises_deterministic_error() -> None:
    service = ProviderConfigurationService()

    with pytest.raises(
        ValueError,
        match="Provider configuration is not registered: missing",
    ):
        service.get("missing")


def test_metadata_defaults_are_not_shared() -> None:
    first = configuration("first")
    second = configuration("second")

    first.metadata["source"] = "first"

    assert first.metadata == {"source": "first"}
    assert second.metadata == {}


def test_configuration_is_immutable() -> None:
    configured = configuration("immutable")

    with pytest.raises(ValidationError):
        configured.display_name = "Changed"


def test_model_serialization_is_deterministic_and_provider_agnostic() -> None:
    first = configuration("serialized")
    second = configuration("serialized")

    first_dump = first.model_dump(mode="json")

    assert first_dump == second.model_dump(mode="json")
    assert set(first_dump) == {
        "provider_id",
        "display_name",
        "api_style",
        "base_url",
        "supports_streaming",
        "supports_tools",
        "supports_json_mode",
        "supports_reasoning",
        "supports_vision",
        "supports_embeddings",
        "supports_audio",
        "default_model",
        "available_models",
        "metadata",
    }
    assert "api_key" not in first_dump
