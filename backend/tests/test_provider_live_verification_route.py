from fastapi.testclient import TestClient

from app.main import app
from app.models.provider_execution import (
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.services import provider_live_verification_service as module


client = TestClient(app)


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


def test_verify_route_reports_unconfigured(monkeypatch) -> None:
    clear_env(monkeypatch)

    response = client.get("/providers/live/verify")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unconfigured"
    assert payload["reachable"] is False


def test_verify_route_reports_reachable_without_exposing_secret(monkeypatch) -> None:
    clear_env(monkeypatch)
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv("STRATUM_PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("STRATUM_PROVIDER_API_KEY", "secret-key")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")

    def fake_run_completion(request):
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content="ok",
            metadata={"transport": {"status_code": 200}},
        )

    monkeypatch.setattr(module, "_run_completion", fake_run_completion)

    response = client.get("/providers/live/verify")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "reachable"
    assert payload["reachable"] is True
    assert payload["http_status"] == 200
    assert "secret-key" not in str(payload)
