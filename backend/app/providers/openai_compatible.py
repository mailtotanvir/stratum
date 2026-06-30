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
        provider_id: str | None = None,
        chat_completions_path: str = "chat/completions",
        request_builder: OpenAIRequestBuilder | None = None,
        response_parser: OpenAIResponseParser | None = None,
        stream_parser: OpenAIStreamParser | None = None,
        protocol_validator: OpenAIProtocolValidator | None = None,
        transport: Transport | None = None,
    ) -> None:
        if provider_id is not None:
            self.provider_id = provider_id
        self._chat_completions_path = _validated_endpoint_path(
            chat_completions_path
        )
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
        protocol_request = self._build_request(request, stream=False)
        response = await self._transport.send(
            _transport_request(
                protocol_request,
                self._chat_completions_path,
            )
        )
        response_body = _decode_response(response)
        result = self._response_parser.parse(response_body, request)
        return result.model_copy(
            update={
                "metadata": {
                    "provider": request.provider,
                    "provider_id": request.provider_id,
                    "model": result.model,
                    "status": result.status.value,
                    "content": result.content,
                    "transport": dict(response.metadata),
                    **result.metadata,
                },
            },
            deep=True,
        )

    async def stream(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        protocol_request = self._build_request(request, stream=True)
        chunks = self._transport.stream(
            _transport_request(
                protocol_request,
                self._chat_completions_path,
            )
        )
        async for event in self._stream_parser.parse(chunks, request):
            yield event

    async def cancel(self, execution_id: str) -> None:
        del execution_id
        raise ProviderAdapterError("Not implemented")

    def _build_request(
        self,
        request: ProviderExecutionRequest,
        *,
        stream: bool,
    ) -> OpenAIChatRequest:
        protocol_request = self._request_builder.build(request)
        protocol_request = protocol_request.model_copy(
            update={"stream": stream},
            deep=True,
        )
        return self._protocol_validator.validate_request(protocol_request)


def _transport_request(
    request: OpenAIChatRequest,
    destination: str,
) -> TransportRequest:
    payload = json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return TransportRequest(
        destination=destination,
        payload=payload,
        metadata={
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
            },
        },
    )


def _validated_endpoint_path(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("chat_completions_path must not be empty")
    return stripped.lstrip("/")


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
