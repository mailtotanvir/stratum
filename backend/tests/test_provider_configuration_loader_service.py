from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)


def test_missing_environment_returns_none() -> None:
    service = ProviderConfigurationService([])
    loader = ProviderConfigurationLoaderService({})

    loaded = loader.load_from_environment(service)

    assert loaded is None
    assert service.list_configurations() == []


def test_loads_new_openai_compatible_provider_from_environment() -> None:
    service = ProviderConfigurationService([])
    loader = ProviderConfigurationLoaderService(
        {
            "STRATUM_PROVIDER_ID": "live",
            "STRATUM_PROVIDER_DISPLAY_NAME": "Live Provider",
            "STRATUM_PROVIDER_BASE_URL": "https://example.test/v1",
            "STRATUM_PROVIDER_API_KEY": "secret-key",
            "STRATUM_PROVIDER_MODEL": "live-model",
            "STRATUM_PROVIDER_ENABLED": "true",
        }
    )

    loaded = loader.load_from_environment(service)

    assert loaded is not None
    assert loaded.provider_id == "live"
    assert loaded.display_name == "Live Provider"
    assert loaded.api_style == "openai-compatible"
    assert loaded.base_url == "https://example.test/v1"
    assert loaded.default_model == "live-model"
    assert loaded.available_models == ["live-model"]
    assert loaded.enabled is True
    assert loaded.metadata["api_key"] == "secret-key"
    assert loaded.metadata["configuration_source"] == "environment"


def test_api_key_is_not_serialized_as_top_level_field() -> None:
    service = ProviderConfigurationService([])
    loader = ProviderConfigurationLoaderService(
        {
            "STRATUM_PROVIDER_ID": "live",
            "STRATUM_PROVIDER_API_KEY": "secret-key",
        }
    )

    loaded = loader.load_from_environment(service)

    assert loaded is not None
    dumped = loaded.model_dump(mode="json")
    assert "api_key" not in dumped
    assert dumped["metadata"]["api_key"] == "secret-key"


def test_default_enabled_is_false() -> None:
    service = ProviderConfigurationService([])
    loader = ProviderConfigurationLoaderService(
        {
            "STRATUM_PROVIDER_ID": "live",
        }
    )

    loaded = loader.load_from_environment(service)

    assert loaded is not None
    assert loaded.enabled is False


def test_updates_existing_provider_configuration() -> None:
    service = ProviderConfigurationService()
    loader = ProviderConfigurationLoaderService(
        {
            "STRATUM_PROVIDER_ID": "openrouter",
            "STRATUM_PROVIDER_DISPLAY_NAME": "OpenRouter Live",
            "STRATUM_PROVIDER_BASE_URL": "https://openrouter.ai/api/v1",
            "STRATUM_PROVIDER_API_KEY": "openrouter-key",
            "STRATUM_PROVIDER_MODEL": "openai/gpt-oss-120b",
            "STRATUM_PROVIDER_ENABLED": "1",
        }
    )

    loaded = loader.load_from_environment(service)
    stored = service.get("openrouter")

    assert loaded == stored
    assert stored.provider_id == "openrouter"
    assert stored.display_name == "OpenRouter Live"
    assert stored.api_style == "openai-compatible"
    assert stored.default_model == "openai/gpt-oss-120b"
    assert stored.available_models == ["openai/gpt-oss-120b"]
    assert stored.enabled is True
    assert stored.metadata["api_key"] == "openrouter-key"


def test_preserves_existing_provider_features_when_updating() -> None:
    service = ProviderConfigurationService()
    before = service.get("openrouter")

    loader = ProviderConfigurationLoaderService(
        {
            "STRATUM_PROVIDER_ID": "openrouter",
            "STRATUM_PROVIDER_MODEL": "some-model",
        }
    )

    after = loader.load_from_environment(service)

    assert after is not None
    assert after.api_style == before.api_style
    assert after.supports_streaming == before.supports_streaming
    assert after.supports_tools == before.supports_tools
    assert after.base_url == before.base_url


def test_repeated_loads_are_deterministic() -> None:
    environment = {
        "STRATUM_PROVIDER_ID": "live",
        "STRATUM_PROVIDER_DISPLAY_NAME": "Live Provider",
        "STRATUM_PROVIDER_BASE_URL": "https://example.test/v1",
        "STRATUM_PROVIDER_API_KEY": "secret-key",
        "STRATUM_PROVIDER_MODEL": "live-model",
        "STRATUM_PROVIDER_ENABLED": "yes",
    }
    service = ProviderConfigurationService([])
    loader = ProviderConfigurationLoaderService(environment)

    first = loader.load_from_environment(service)
    second = loader.load_from_environment(service)

    assert first == second
    assert len(service.list_configurations()) == 1


def test_does_not_modify_builtin_registry_when_nothing_configured() -> None:
    service = ProviderConfigurationService()
    before = service.snapshot()

    loader = ProviderConfigurationLoaderService({})
    loaded = loader.load_from_environment(service)

    assert loaded is None
    assert service.snapshot() == before
