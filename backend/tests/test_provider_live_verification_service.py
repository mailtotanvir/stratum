from datetime import datetime

from app.models.provider_execution import (
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderUsage,
)
from app.services import provider_live_verification_service as module
from app.services.provider_live_verification_service import (
    ProviderLiveVerificationService,
)


def clear_env(monkeypatch) -> None:
    for name in [
        "STRATUM_PROVIDER_ID",
        "STRATUM_PROVIDER_DISPLAY_NAME",
        "STRATUM_PROVIDER_BASE_URL",
        "STRATUM_PROVIDER_API_KEY",
        "STRATUM_PROVIDER_MODEL",
        "STRATUM_PROVIDER_ENABLED",
    ]:
        monkeypatch.delenv(name, raising=False)


def configure(monkeypatch) -> None:
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv("STRATUM_PROVIDER_DISPLAY_NAME", "OpenRouter")
    monkeypatch.setenv("STRATUM_PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("STRATUM_PROVIDER_API_KEY", "secret-key")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")


def test_verify_reports_unconfigured_without_network(monkeypatch) -> None:
    clear_env(monkeypatch)

    verification = ProviderLiveVerificationService().verify()

    assert verification.status == "unconfigured"
    assert verification.reachable is False
    assert verification.error_type == "ProviderConfigurationError"
    assert verification.provider_id is None


def test_verify_reports_configuration_error_without_network(monkeypatch) -> None:
    clear_env(monkeypatch)
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv("STRATUM_PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")

    verification = ProviderLiveVerificationService().verify()

    assert verification.status == "configuration_error"
    assert verification.reachable is False
    assert verification.provider_id == "openrouter"
    assert verification.error_message == (
        "Missing required provider configuration: api_key"
    )


def test_verify_reports_reachable_provider(monkeypatch) -> None:
    clear_env(monkeypatch)
    configure(monkeypatch)

    def fake_run_completion(request):
        assert request.provider == "openrouter"
        assert request.model == "openai/gpt-oss-120b"
        assert request.max_tokens == 32
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content="Stratum provider verification passed.",
            usage=ProviderUsage(total_tokens=8),
            metadata={"transport": {"status_code": 200}},
        )

    monkeypatch.setattr(module, "_run_completion", fake_run_completion)

    verification = ProviderLiveVerificationService().verify()

    assert verification.status == "reachable"
    assert verification.reachable is True
    assert verification.provider_id == "openrouter"
    assert verification.model == "openai/gpt-oss-120b"
    assert verification.http_status == 200
    assert verification.content_preview == (
        "Stratum provider verification passed."
    )
    assert verification.error_type is None
    assert isinstance(verification.verified_at, datetime)


def test_verify_reports_authentication_failure(monkeypatch) -> None:
    clear_env(monkeypatch)
    configure(monkeypatch)

    def fake_run_completion(_request):
        raise RuntimeError("HTTP transport failed with status 401")

    monkeypatch.setattr(module, "_run_completion", fake_run_completion)

    verification = ProviderLiveVerificationService().verify()

    assert verification.status == "authentication_failed"
    assert verification.reachable is False
    assert verification.error_type == "RuntimeError"
    assert "401" in verification.error_message


def test_verify_reports_rate_limit(monkeypatch) -> None:
    clear_env(monkeypatch)
    configure(monkeypatch)

    def fake_run_completion(_request):
        raise RuntimeError("HTTP transport failed with status 429")

    monkeypatch.setattr(module, "_run_completion", fake_run_completion)

    verification = ProviderLiveVerificationService().verify()

    assert verification.status == "rate_limited"
    assert verification.reachable is False
