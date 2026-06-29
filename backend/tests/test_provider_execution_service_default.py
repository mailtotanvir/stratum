from app.services.provider_execution_service import (
    provider_execution_service_default,
)


def test_provider_execution_service_default_preserves_fake_adapter_without_environment(
    monkeypatch,
) -> None:
    monkeypatch.delenv("STRATUM_PROVIDER_ID", raising=False)
    monkeypatch.delenv("STRATUM_PROVIDER_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("STRATUM_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("STRATUM_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("STRATUM_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("STRATUM_PROVIDER_ENABLED", raising=False)

    service = provider_execution_service_default()

    assert service._adapter_registry.has_adapter("fake") is True
    assert service._adapter_registry.has_adapter("openai-compatible") is False


def test_provider_execution_service_default_registers_enabled_live_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv("STRATUM_PROVIDER_DISPLAY_NAME", "OpenRouter")
    monkeypatch.setenv(
        "STRATUM_PROVIDER_BASE_URL",
        "https://openrouter.ai/api/v1",
    )
    monkeypatch.setenv("STRATUM_PROVIDER_API_KEY", "secret-key")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "test-model")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")

    service = provider_execution_service_default()

    assert service._adapter_registry.has_adapter("fake") is True
    assert service._adapter_registry.has_adapter("openrouter") is True
    assert service._adapter_registry.has_adapter("openai-compatible") is False


def test_provider_execution_service_default_skips_disabled_live_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv("STRATUM_PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "test-model")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "false")

    service = provider_execution_service_default()

    assert service._adapter_registry.has_adapter("fake") is True
    assert service._adapter_registry.has_adapter("openrouter") is False
