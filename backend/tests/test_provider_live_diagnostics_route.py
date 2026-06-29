from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def clear_env(monkeypatch) -> None:
    for name in [
        "STRATUM_PROVIDER_ID",
        "STRATUM_PROVIDER_DISPLAY_NAME",
        "STRATUM_PROVIDER_BASE_URL",
        "STRATUM_PROVIDER_API_KEY",
        "STRATUM_PROVIDER_MODEL",
        "STRATUM_PROVIDER_ENABLED",
        "STRATUM_PROVIDER_ENDPOINT_PATH",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_provider_live_diagnostics_route_reports_unconfigured_environment(
    monkeypatch,
) -> None:
    clear_env(monkeypatch)

    response = client.get("/providers/live/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["ready"] is False
    assert payload["has_api_key"] is False
    assert payload["issues"] == [
        "No live provider environment configuration found."
    ]


def test_provider_live_diagnostics_route_reports_ready_provider(
    monkeypatch,
) -> None:
    clear_env(monkeypatch)
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv("STRATUM_PROVIDER_DISPLAY_NAME", "OpenRouter")
    monkeypatch.setenv(
        "STRATUM_PROVIDER_BASE_URL",
        "https://openrouter.ai/api/v1",
    )
    monkeypatch.setenv("STRATUM_PROVIDER_API_KEY", "secret-key")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")

    response = client.get("/providers/live/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["ready"] is True
    assert payload["provider_id"] == "openrouter"
    assert payload["display_name"] == "OpenRouter"
    assert payload["base_url"] == "https://openrouter.ai/api/v1"
    assert payload["default_model"] == "openai/gpt-oss-120b"
    assert payload["has_api_key"] is True
    assert payload["issues"] == []
    assert "secret-key" not in str(payload)


def test_provider_live_diagnostics_route_reports_missing_api_key(
    monkeypatch,
) -> None:
    clear_env(monkeypatch)
    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv(
        "STRATUM_PROVIDER_BASE_URL",
        "https://openrouter.ai/api/v1",
    )
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")

    response = client.get("/providers/live/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["ready"] is False
    assert payload["has_api_key"] is False
    assert payload["issues"] == [
        "Missing required provider configuration: api_key"
    ]
