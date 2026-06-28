import pytest

from app.providers.fake import FakeProviderAdapter
from app.services.provider_adapter_registry_service import (
    ProviderAdapterRegistryService,
)


def test_registry_includes_fake_adapter() -> None:
    adapters = ProviderAdapterRegistryService().list_adapters()

    assert [adapter.provider_id for adapter in adapters] == ["fake"]


def test_list_adapters_is_deterministic() -> None:
    registry = ProviderAdapterRegistryService()

    first = registry.list_adapters()
    second = registry.list_adapters()

    assert [adapter.provider_id for adapter in first] == ["fake"]
    assert [adapter.provider_id for adapter in second] == ["fake"]
    assert first[0] is second[0]


def test_get_fake_adapter() -> None:
    adapter = ProviderAdapterRegistryService().get_adapter("fake")

    assert isinstance(adapter, FakeProviderAdapter)
    assert adapter.provider_id == "fake"


def test_has_adapter_for_known_and_unknown_provider_ids() -> None:
    registry = ProviderAdapterRegistryService()

    assert registry.has_adapter("fake") is True
    assert registry.has_adapter("missing") is False


def test_unknown_provider_id_raises_clear_error() -> None:
    registry = ProviderAdapterRegistryService()

    with pytest.raises(
        ValueError,
        match="Provider adapter is not registered: missing",
    ):
        registry.get_adapter("missing")


def test_duplicate_provider_id_registration_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Provider adapter already registered: fake",
    ):
        ProviderAdapterRegistryService(
            [FakeProviderAdapter(), FakeProviderAdapter()]
        )


def test_registry_does_not_include_real_providers() -> None:
    provider_ids = [
        adapter.provider_id
        for adapter in ProviderAdapterRegistryService().list_adapters()
    ]

    assert provider_ids == ["fake"]
    assert "openai" not in provider_ids
    assert "anthropic" not in provider_ids
    assert "openai-compatible" not in provider_ids
