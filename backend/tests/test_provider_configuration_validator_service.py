import pytest

from app.models.provider_configuration import ProviderConfiguration
from app.services.provider_configuration_validator_service import (
    ProviderConfigurationError,
    ProviderConfigurationValidatorService,
)


def configuration(**overrides) -> ProviderConfiguration:
    data = {
        "provider_id": "live",
        "display_name": "Live",
        "api_style": "openai-compatible",
        "base_url": "https://example.test/v1",
        "default_model": "live-model",
        "available_models": ["live-model"],
        "enabled": True,
        "metadata": {"api_key": "secret-key"},
    }
    data.update(overrides)
    return ProviderConfiguration(**data)


def test_valid_live_configuration_passes() -> None:
    ProviderConfigurationValidatorService().validate_for_live_execution(
        configuration()
    )


def test_disabled_provider_fails() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="Provider is not enabled",
    ):
        ProviderConfigurationValidatorService().validate_for_live_execution(
            configuration(enabled=False)
        )


def test_unsupported_api_style_fails() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="Unsupported provider api_style",
    ):
        ProviderConfigurationValidatorService().validate_for_live_execution(
            configuration(api_style="anthropic")
        )


def test_missing_base_url_fails() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="base_url",
    ):
        ProviderConfigurationValidatorService().validate_for_live_execution(
            configuration(base_url=None)
        )


def test_missing_default_model_fails() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="default_model",
    ):
        ProviderConfigurationValidatorService().validate_for_live_execution(
            configuration(default_model=None, available_models=[])
        )


def test_missing_api_key_fails() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="api_key",
    ):
        ProviderConfigurationValidatorService().validate_for_live_execution(
            configuration(metadata={})
        )


def test_blank_api_key_fails() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="api_key",
    ):
        ProviderConfigurationValidatorService().validate_for_live_execution(
            configuration(metadata={"api_key": "   "})
        )
