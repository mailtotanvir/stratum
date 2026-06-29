from app.models.provider_configuration import ProviderConfiguration
from app.services.provider_authentication_service import (
    ProviderAuthenticationService,
)


def configuration(metadata: dict | None = None) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider_id="live",
        display_name="Live",
        api_style="openai-compatible",
        base_url="https://example.test/v1",
        metadata=metadata or {},
    )


def test_headers_for_returns_bearer_auth_header_from_metadata_api_key() -> None:
    headers = ProviderAuthenticationService().headers_for(
        configuration({"api_key": "secret-key"})
    )

    assert headers == {"Authorization": "Bearer secret-key"}


def test_headers_for_returns_empty_headers_without_api_key() -> None:
    headers = ProviderAuthenticationService().headers_for(configuration())

    assert headers == {}


def test_api_key_trims_whitespace() -> None:
    key = ProviderAuthenticationService().api_key(
        configuration({"api_key": "  secret-key  "})
    )

    assert key == "secret-key"


def test_blank_api_key_is_ignored() -> None:
    service = ProviderAuthenticationService()
    config = configuration({"api_key": "   "})

    assert service.api_key(config) is None
    assert service.headers_for(config) == {}


def test_api_key_is_not_serialized_as_top_level_field() -> None:
    config = configuration({"api_key": "secret-key"})

    dumped = config.model_dump(mode="json")

    assert "api_key" not in dumped
    assert dumped["metadata"]["api_key"] == "secret-key"
