from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def clear(monkeypatch):
    for key in [
        "STRATUM_PROVIDER_ID",
        "STRATUM_PROVIDER_DISPLAY_NAME",
        "STRATUM_PROVIDER_BASE_URL",
        "STRATUM_PROVIDER_API_KEY",
        "STRATUM_PROVIDER_MODEL",
        "STRATUM_PROVIDER_ENABLED",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_provider_health_unconfigured(monkeypatch):
    clear(monkeypatch)

    r = client.get("/providers/health")

    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "unconfigured"
    assert body["ready"] is False


def test_provider_health_ready(monkeypatch):
    clear(monkeypatch)

    monkeypatch.setenv("STRATUM_PROVIDER_ID", "openrouter")
    monkeypatch.setenv(
        "STRATUM_PROVIDER_BASE_URL",
        "https://openrouter.ai/api/v1",
    )
    monkeypatch.setenv("STRATUM_PROVIDER_API_KEY", "secret")
    monkeypatch.setenv("STRATUM_PROVIDER_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("STRATUM_PROVIDER_ENABLED", "true")

    r = client.get("/providers/health")

    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "ready"
    assert body["supports_completion"] is True
    assert body["supports_streaming"] is True
