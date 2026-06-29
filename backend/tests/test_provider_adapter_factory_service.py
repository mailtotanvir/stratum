import asyncio
from collections.abc import AsyncIterator

import pytest

from app.models.provider_configuration import ProviderConfiguration
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
)
from app.providers.openai_compatible import OpenAICompatibleProviderAdapter
from app.providers.transport import (
    Transport,
    TransportRequest,
    TransportResponse,
)
from app.services.provider_adapter_factory_service import (
    ProviderAdapterFactoryService,
)


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
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"Live factory response."}}]}'
            )
        )

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self.request = request
        yield (
            b'data: {"choices":[{"delta":{"content":"Hello"},'
            b'"finish_reason":null}]}\n\n'
        )
        yield b'data: [DONE]\n\n'


def configuration(**overrides) -> ProviderConfiguration:
    data = {
        "provider_id": "openrouter",
        "display_name": "OpenRouter",
        "api_style": "openai-compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "supports_streaming": True,
        "default_model": "test-model",
        "available_models": ["test-model"],
        "enabled": True,
        "metadata": {"api_key": "secret-key"},
    }
    data.update(overrides)
    return ProviderConfiguration(**data)


def request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="openrouter",
        model="test-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Hello.",
            )
        ],
    )


def test_factory_creates_openai_compatible_adapter_with_provider_id() -> None:
    adapter = ProviderAdapterFactoryService().create(
        configuration(),
        transport=SpyTransport(),
    )

    assert isinstance(adapter, OpenAICompatibleProviderAdapter)
    assert adapter.provider_id == "openrouter"


def test_factory_configures_transport_endpoint_and_auth_headers() -> None:
    spy = SpyTransport()
    adapter = ProviderAdapterFactoryService().create(
        configuration(),
        transport=spy,
    )

    result = asyncio.run(adapter.complete(request()))

    assert result.content == "Live factory response."
    assert spy.request is not None
    assert spy.request.destination == (
        "https://openrouter.ai/api/v1/chat/completions"
    )
    assert spy.request.metadata["headers"]["Authorization"] == (
        "Bearer secret-key"
    )
    assert spy.request.metadata["headers"]["Content-Type"] == (
        "application/json"
    )


def test_factory_rejects_provider_without_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="api_key",
    ):
        ProviderAdapterFactoryService().create(
            configuration(metadata={}),
            transport=SpyTransport(),
        )


def test_factory_rejects_unsupported_api_style() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported provider api_style",
    ):
        ProviderAdapterFactoryService().create(
            configuration(api_style="anthropic"),
            transport=SpyTransport(),
        )


def test_factory_rejects_missing_base_url() -> None:
    with pytest.raises(
        ValueError,
        match="base_url",
    ):
        ProviderAdapterFactoryService().create(
            configuration(base_url=None),
            transport=SpyTransport(),
        )


def test_factory_uses_custom_chat_completions_path_from_metadata() -> None:
    spy = SpyTransport()
    adapter = ProviderAdapterFactoryService().create(
        configuration(
            metadata={
                "api_key": "secret-key",
                "chat_completions_path": "custom/chat",
            }
        ),
        transport=spy,
    )

    asyncio.run(adapter.complete(request()))

    assert spy.request is not None
    assert spy.request.destination == (
        "https://openrouter.ai/api/v1/custom/chat"
    )
