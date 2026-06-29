import json
from collections.abc import AsyncIterator

from app.models.openai_protocol import OpenAIChatRequest
from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStreamEvent,
)
from app.providers.base import ProviderAdapter, ProviderAdapterError
from app.providers.fake_openai_compatible_transport import (
    FakeOpenAICompatibleTransport,
)
from app.providers.transport import (
    Transport,
    TransportRequest,
    TransportResponse,
)
from app.services.openai_protocol_validator import (
    OpenAIProtocolValidator,
)
from app.services.openai_request_builder import OpenAIRequestBuilder
from app.services.openai_response_parser import (
    OpenAIResponseParser,
    OpenAIResponseParserError,
)
from app.services.openai_stream_parser import OpenAIStreamParser


class OpenAICompatibleProviderAdapter(ProviderAdapter):
    provider_id = "openai-compatible"

    def __init__(
        self,
        *,
        request_builder: OpenAIRequestBuilder | None = None,
        response_parser: OpenAIResponseParser | None = None,
        stream_parser: OpenAIStreamParser | None = None,
        protocol_validator: OpenAIProtocolValidator | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._request_builder = request_builder or OpenAIRequestBuilder()
        self._protocol_validator = (
            protocol_validator or OpenAIProtocolValidator()
        )
        self._response_parser = response_parser or OpenAIResponseParser(
            self._protocol_validator
        )
        self._stream_parser = stream_parser or OpenAIStreamParser(
            self._protocol_validator
        )
        self._transport = transport or FakeOpenAICompatibleTransport()

    async def complete(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        protocol_request = self._build_request(request)
        response = await self._transport.send(
            _transport_request(protocol_request)
        )
        response_body = _decode_response(response)
        return self._response_parser.parse(response_body, request)

    async def stream(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        protocol_request = self._build_request(request)
        chunks = self._transport.stream(
            _transport_request(protocol_request)
        )
        async for event in self._stream_parser.parse(chunks, request):
            yield event

    async def cancel(self, execution_id: str) -> None:
        del execution_id
        raise ProviderAdapterError("Not implemented")

    def _build_request(
        self,
        request: ProviderExecutionRequest,
    ) -> OpenAIChatRequest:
        protocol_request = self._request_builder.build(request)
        return self._protocol_validator.validate_request(protocol_request)


def _transport_request(
    request: OpenAIChatRequest,
) -> TransportRequest:
    payload = json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return TransportRequest(
        destination="chat/completions",
        payload=payload,
    )


def _decode_response(response: TransportResponse) -> dict:
    try:
        payload = json.loads(response.payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenAIResponseParserError(
            "Malformed OpenAI-compatible chat response."
        ) from exc
    if not isinstance(payload, dict):
        raise OpenAIResponseParserError(
            "Malformed OpenAI-compatible chat response."
        )
    return payload
