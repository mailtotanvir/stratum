from app.models.provider_configuration import ProviderConfiguration
from app.providers.base import ProviderAdapter
from app.providers.fake import FakeProviderAdapter
from app.services.live_provider_adapter_registry_service import (
    LiveProviderAdapterRegistryService,
)
from app.services.provider_adapter_registry_service import (
    ProviderAdapterRegistryService,
)
from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)


class DummyAdapter(ProviderAdapter):
    provider_id = "live"

    async def complete(self, request):
        raise NotImplementedError

    async def stream(self, request):
        if False:
            yield None
        raise NotImplementedError


class DummyFactory:
    def __init__(self) -> None:
        self.configurations = []

    def create(self, configuration: ProviderConfiguration) -> ProviderAdapter:
        self.configurations.append(configuration)
        adapter = DummyAdapter()
        adapter.provider_id = configuration.provider_id
        return adapter


def configuration(
    provider_id: str,
    *,
    enabled: bool = True,
    api_style: str = "openai-compatible",
    base_url: str | None = "https://example.test/v1",
) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider_id=provider_id,
        display_name=provider_id.title(),
        api_style=api_style,
        base_url=base_url,
        enabled=enabled,
        default_model="test-model",
        available_models=["test-model"],
    )


def test_build_registry_includes_fake_and_enabled_live_provider() -> None:
    config_service = ProviderConfigurationService(
        [
            configuration("live"),
        ]
    )
    factory = DummyFactory()

    registry = LiveProviderAdapterRegistryService(
        configuration_service=config_service,
        factory=factory,
    ).build_registry()

    assert [
        adapter.provider_id
        for adapter in registry.list_adapters()
    ] == ["fake", "live"]
    assert isinstance(registry.get_adapter("fake"), FakeProviderAdapter)
    assert registry.get_adapter("live").provider_id == "live"
    assert [item.provider_id for item in factory.configurations] == ["live"]


def test_build_registry_skips_disabled_provider() -> None:
    config_service = ProviderConfigurationService(
        [
            configuration("disabled", enabled=False),
        ]
    )
    factory = DummyFactory()

    registry = LiveProviderAdapterRegistryService(
        configuration_service=config_service,
        factory=factory,
    ).build_registry()

    assert [
        adapter.provider_id
        for adapter in registry.list_adapters()
    ] == ["fake"]
    assert factory.configurations == []


def test_build_registry_skips_provider_without_base_url() -> None:
    config_service = ProviderConfigurationService(
        [
            configuration("missing-url", base_url=None),
        ]
    )
    factory = DummyFactory()

    registry = LiveProviderAdapterRegistryService(
        configuration_service=config_service,
        factory=factory,
    ).build_registry()

    assert [
        adapter.provider_id
        for adapter in registry.list_adapters()
    ] == ["fake"]
    assert factory.configurations == []


def test_build_registry_skips_non_openai_compatible_provider() -> None:
    config_service = ProviderConfigurationService(
        [
            configuration("anthropic", api_style="anthropic"),
        ]
    )
    factory = DummyFactory()

    registry = LiveProviderAdapterRegistryService(
        configuration_service=config_service,
        factory=factory,
    ).build_registry()

    assert [
        adapter.provider_id
        for adapter in registry.list_adapters()
    ] == ["fake"]
    assert factory.configurations == []


def test_build_registry_accepts_custom_base_adapters() -> None:
    config_service = ProviderConfigurationService(
        [
            configuration("live"),
        ]
    )
    factory = DummyFactory()
    base = DummyAdapter()
    base.provider_id = "base"

    registry = LiveProviderAdapterRegistryService(
        configuration_service=config_service,
        factory=factory,
    ).build_registry(base_adapters=[base])

    assert [
        adapter.provider_id
        for adapter in registry.list_adapters()
    ] == ["base", "live"]


def test_from_environment_loads_configuration_before_building_registry() -> None:
    config_service = ProviderConfigurationService([])
    loader = ProviderConfigurationLoaderService(
        {
            "STRATUM_PROVIDER_ID": "env-live",
            "STRATUM_PROVIDER_BASE_URL": "https://example.test/v1",
            "STRATUM_PROVIDER_MODEL": "env-model",
            "STRATUM_PROVIDER_ENABLED": "true",
        }
    )
    factory = DummyFactory()

    service = LiveProviderAdapterRegistryService.from_environment(
        configuration_service=config_service,
        loader=loader,
        factory=factory,
    )
    registry = service.build_registry()

    assert [
        adapter.provider_id
        for adapter in registry.list_adapters()
    ] == ["env-live", "fake"]
    assert config_service.get("env-live").default_model == "env-model"
    assert [item.provider_id for item in factory.configurations] == [
        "env-live"
    ]


def test_provider_adapter_registry_public_register_rejects_duplicates() -> None:
    registry = ProviderAdapterRegistryService([FakeProviderAdapter()])

    try:
        registry.register(FakeProviderAdapter())
    except ValueError as exc:
        assert str(exc) == "Provider adapter already registered: fake"
    else:
        raise AssertionError("duplicate adapter registration was not rejected")
