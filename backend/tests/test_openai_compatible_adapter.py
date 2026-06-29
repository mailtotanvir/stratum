import asyncio
from collections.abc import AsyncIterator

import pytest

from app.models.openai_protocol import OpenAIChatRequest
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderExecutionStreamEvent,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.providers.fake_openai_compatible_transport import (
    FAKE_OPENAI_CONTENT,
    FakeOpenAICompatibleTransport,
)
from app.providers.openai_compatible import (
    OpenAICompatibleProviderAdapter,
)
from app.providers.transport import (
    Transport,
    TransportError,
    TransportRequest,
    TransportResponse,
)
from app.services.openai_response_parser import (
    OpenAIResponseParserError,
)


def request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="openai-compatible",
        model="test-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Execute.",
            )
        ],
        stream_mode=ProviderStreamMode.SSE,
    )


async def collect(
    adapter: OpenAICompatibleProviderAdapter,
    execution_request: ProviderExecutionRequest,
) -> list[ProviderExecutionStreamEvent]:
    return [
        event
        async for event in adapter.stream(execution_request)
    ]


def test_complete_uses_fake_protocol_pipeline() -> None:
    result = asyncio.run(
        OpenAICompatibleProviderAdapter().complete(request())
    )

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.provider == "openai-compatible"
    assert result.model == "test-model"
    assert result.content == FAKE_OPENAI_CONTENT
    assert result.usage is not None
    assert result.usage.total_tokens == 7


def test_stream_uses_fake_protocol_pipeline() -> None:
    events = asyncio.run(
        collect(OpenAICompatibleProviderAdapter(), request())
    )

    assert [event.event_type for event in events] == [
        "delta",
        "delta",
        "completed",
    ]
    assert [event.content for event in events] == [
        None,
        FAKE_OPENAI_CONTENT,
        None,
    ]


class SpyBuilder:
    def __init__(self) -> None:
        self.request = None

    def build(
        self,
        execution_request: ProviderExecutionRequest,
    ) -> OpenAIChatRequest:
        self.request = execution_request
        return OpenAIChatRequest(
            model=execution_request.model,
            messages=[],
            stream=False,
        )


class SpyValidator:
    def __init__(self) -> None:
        self.request = None

    def validate_request(
        self,
        protocol_request: OpenAIChatRequest,
    ) -> OpenAIChatRequest:
        self.request = protocol_request
        return protocol_request


class SpyTransport(Transport):
    def __init__(self) -> None:
        self.request = None

    async def send(
        self,
        transport_request: TransportRequest,
    ) -> TransportResponse:
        self.request = transport_request
        return TransportResponse(
            payload=(
                b'{"choices":[{"message":{"role":"assistant",'
                b'"content":"Injected."}}]}'
            )
        )

    async def stream(
        self,
        transport_request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self.request = transport_request
        yield (
            b'{"choices":[{"delta":{},'
            b'"finish_reason":"stop"}]}'
        )


class SpyResponseParser:
    def __init__(self) -> None:
        self.called = False

    def parse(self, response_body, execution_request):
        self.called = True
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=execution_request.provider,
            model=execution_request.model,
            content=response_body["choices"][0]["message"]["content"],
        )


def test_complete_uses_injected_dependencies() -> None:
    builder = SpyBuilder()
    validator = SpyValidator()
    transport = SpyTransport()
    parser = SpyResponseParser()
    execution_request = request()
    adapter = OpenAICompatibleProviderAdapter(
        request_builder=builder,
        response_parser=parser,
        protocol_validator=validator,
        transport=transport,
    )

    result = asyncio.run(adapter.complete(execution_request))

    assert result.content == "Injected."
    assert builder.request is execution_request
    assert validator.request is not None
    assert transport.request is not None
    assert parser.called is True


def test_fake_transport_error_propagates() -> None:
    adapter = OpenAICompatibleProviderAdapter(
        transport=FakeOpenAICompatibleTransport(
            error_message="Transport failed."
        )
    )

    with pytest.raises(TransportError, match="Transport failed"):
        asyncio.run(adapter.complete(request()))


def test_parser_error_propagates() -> None:
    adapter = OpenAICompatibleProviderAdapter(
        transport=FakeOpenAICompatibleTransport(
            malformed_response=True,
        )
    )

    with pytest.raises(OpenAIResponseParserError):
        asyncio.run(adapter.complete(request()))


def test_request_is_not_mutated_and_result_is_deterministic() -> None:
    adapter = OpenAICompatibleProviderAdapter()
    execution_request = request()
    before = execution_request.model_dump(mode="json")

    first = asyncio.run(adapter.complete(execution_request))
    second = asyncio.run(adapter.complete(execution_request))

    assert execution_request.model_dump(mode="json") == before
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
