from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_live_diagnostics_service import (
    ProviderLiveDiagnosticsService,
)


def test_diagnostics_reports_unconfigured_environment() -> None:
    diagnostics = ProviderLiveDiagnosticsService(
        loader=ProviderConfigurationLoaderService({}),
    ).inspect_environment()

    assert diagnostics.configured is False
    assert diagnostics.ready is False
    assert diagnostics.provider_id is None
    assert diagnostics.has_api_key is False
    assert diagnostics.issues == [
        "No live provider environment configuration found."
    ]


def test_diagnostics_reports_ready_live_provider_without_exposing_secret() -> None:
    diagnostics = ProviderLiveDiagnosticsService(
        loader=ProviderConfigurationLoaderService(
            {
                "STRATUM_PROVIDER_ID": "openrouter",
                "STRATUM_PROVIDER_DISPLAY_NAME": "OpenRouter",
                "STRATUM_PROVIDER_BASE_URL": "https://openrouter.ai/api/v1",
                "STRATUM_PROVIDER_API_KEY": "secret-key",
                "STRATUM_PROVIDER_MODEL": "openai/gpt-oss-120b",
                "STRATUM_PROVIDER_ENABLED": "true",
            }
        ),
    ).inspect_environment()

    assert diagnostics.configured is True
    assert diagnostics.ready is True
    assert diagnostics.provider_id == "openrouter"
    assert diagnostics.display_name == "OpenRouter"
    assert diagnostics.api_style == "openai-compatible"
    assert diagnostics.base_url == "https://openrouter.ai/api/v1"
    assert diagnostics.default_model == "openai/gpt-oss-120b"
    assert diagnostics.enabled is True
    assert diagnostics.has_api_key is True
    assert diagnostics.issues == []

    dumped = diagnostics.model_dump(mode="json")
    assert "secret-key" not in str(dumped)


def test_diagnostics_reports_validation_issue_for_missing_api_key() -> None:
    diagnostics = ProviderLiveDiagnosticsService(
        loader=ProviderConfigurationLoaderService(
            {
                "STRATUM_PROVIDER_ID": "openrouter",
                "STRATUM_PROVIDER_BASE_URL": "https://openrouter.ai/api/v1",
                "STRATUM_PROVIDER_MODEL": "openai/gpt-oss-120b",
                "STRATUM_PROVIDER_ENABLED": "true",
            }
        ),
    ).inspect_environment()

    assert diagnostics.configured is True
    assert diagnostics.ready is False
    assert diagnostics.provider_id == "openrouter"
    assert diagnostics.has_api_key is False
    assert diagnostics.issues == [
        "Missing required provider configuration: api_key"
    ]


def test_diagnostics_reports_validation_issue_for_disabled_provider() -> None:
    diagnostics = ProviderLiveDiagnosticsService(
        loader=ProviderConfigurationLoaderService(
            {
                "STRATUM_PROVIDER_ID": "openrouter",
                "STRATUM_PROVIDER_BASE_URL": "https://openrouter.ai/api/v1",
                "STRATUM_PROVIDER_API_KEY": "secret-key",
                "STRATUM_PROVIDER_MODEL": "openai/gpt-oss-120b",
                "STRATUM_PROVIDER_ENABLED": "false",
            }
        ),
    ).inspect_environment()

    assert diagnostics.configured is True
    assert diagnostics.ready is False
    assert diagnostics.enabled is False
    assert diagnostics.issues == [
        "Provider is not enabled for live execution: openrouter"
    ]


def test_diagnostics_includes_configured_endpoint_path() -> None:
    diagnostics = ProviderLiveDiagnosticsService(
        loader=ProviderConfigurationLoaderService(
            {
                "STRATUM_PROVIDER_ID": "live",
                "STRATUM_PROVIDER_BASE_URL": "https://example.test/v1",
                "STRATUM_PROVIDER_API_KEY": "secret-key",
                "STRATUM_PROVIDER_MODEL": "live-model",
                "STRATUM_PROVIDER_ENABLED": "true",
                "STRATUM_PROVIDER_ENDPOINT_PATH": "/custom/chat",
            }
        ),
    ).inspect_environment()

    assert diagnostics.ready is True
    assert diagnostics.metadata["configuration_source"] == "environment"
    assert diagnostics.metadata["chat_completions_path"] == "/custom/chat"
