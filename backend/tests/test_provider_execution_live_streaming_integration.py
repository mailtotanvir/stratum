import asyncio
from collections.abc import AsyncIterator

from app.models.provider_configuration import ProviderConfiguration
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
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


class SpyStreamingTransport(Transport):
    def __init__(self) -> None:
        self.request: TransportRequest | None = None

    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        self.request = request
        return TransportResponse(payload=b"{}")

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self.request = request
        yield (
            b'data: {"id":"chatcmpl_test","object":"chat.completion.chunk",'
            b'"created":1,"model":"live-model","choices":[{"index":0,'
            b'"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
        )
        yield (
            b'data: {"id":"chatcmpl_test","object":"chat.completion.chunk",'
            b'"created":1,"model":"live-model","choices":[{"index":0,'
            b'"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
        )
        yield (
            b'data: {"id":"chatcmpl_test","object":"chat.completion.chunk",'
            b'"created":1,"model":"live-model","choices":[{"index":0,'
            b'"delta":{"content":" world"},"finish_reason":null}]}\n\n'
        )
        yield (
            b'data: {"id":"chatcmpl_test","object":"chat.completion.chunk",'
            b'"created":1,"model":"live-model","choices":[{"index":0,'
            b'"delta":{},"finish_reason":"stop"}]}\n\n'
        )
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
                content="Stream hello.",
            )
        ],
        stream_mode=ProviderStreamMode.SSE,
    )


def test_provider_execution_service_streams_through_live_configured_adapter() -> None:
    async def run() -> None:
        spy_transport = SpyStreamingTransport()
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

        events = [
            event
            async for event in service.stream(execution_request())
        ]

        assert [event.event_type for event in events] == [
            "delta",
            "delta",
            "delta",
            "completed",
        ]
        assert [event.content for event in events] == [
            None,
            "Hello",
            " world",
            None,
        ]
        assert [event.sequence for event in events] == [0, 1, 2, 3]

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

    asyncio.run(run())
