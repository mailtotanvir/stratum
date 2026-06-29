import asyncio
from collections.abc import AsyncIterator

from app.models.provider_configuration import ProviderConfiguration
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
)
from app.providers.transport import (
    Transport,
    TransportRequest,
    TransportResponse,
)
from app.services.live_provider_adapter_registry_service import (
    LiveProviderAdapterRegistryService,
)
from app.services.provider_adapter_factory_service import (
    ProviderAdapterFactoryService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)
from app.services.provider_execution_service import ProviderExecutionService


class SpyTransport(Transport):
    def __init__(self) -> None:
        self.request: TransportRequest | None = None

    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        self.request = request
        return TransportResponse(
            payload=(
                b'{"id":"chatcmpl_test","object":"chat.completion",'
                b'"created":1,"model":"live-model",'
                b'"choices":[{"index":0,"message":{"role":"assistant",'
                b'"content":"Live adapter path works."},'
                b'"finish_reason":"stop"}],'
                b'"usage":{"prompt_tokens":3,"completion_tokens":4,'
                b'"total_tokens":7}}'
            ),
            metadata={"status_code": 200},
        )

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self.request = request
        yield b"data: [DONE]\n\n"


class SpyFactory(ProviderAdapterFactoryService):
    def __init__(self, transport: Transport) -> None:
        super().__init__()
        self._transport = transport

    def create(self, configuration: ProviderConfiguration):
        return super().create(
            configuration,
            transport=self._transport,
        )


def live_configuration() -> ProviderConfiguration:
    return ProviderConfiguration(
        provider_id="live",
        display_name="Live Provider",
        api_style="openai-compatible",
        base_url="https://example.test/v1",
        supports_streaming=True,
        default_model="live-model",
        available_models=["live-model"],
        enabled=True,
        metadata={"api_key": "secret-key"},
    )


def execution_request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="live",
        model="live-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Say hello.",
            )
        ],
    )


def test_provider_execution_service_completes_through_live_configured_adapter() -> None:
    spy_transport = SpyTransport()
    configuration_service = ProviderConfigurationService(
        [live_configuration()]
    )
    adapter_registry = LiveProviderAdapterRegistryService(
        configuration_service=configuration_service,
        factory=SpyFactory(spy_transport),
    ).build_registry()

    service = ProviderExecutionService(
        adapter_registry=adapter_registry,
    )

    result = asyncio.run(service.complete(execution_request()))

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.provider == "live"
    assert result.model == "live-model"
    assert result.content == "Live adapter path works."
    assert result.usage is not None
    assert result.usage.total_tokens == 7

    assert spy_transport.request is not None
    assert spy_transport.request.destination == (
        "https://example.test/v1/chat/completions"
    )
    assert spy_transport.request.metadata["headers"]["Authorization"] == (
        "Bearer secret-key"
    )
    assert spy_transport.request.metadata["headers"]["Content-Type"] == (
        "application/json"
    )
