import asyncio

import pytest
from pydantic import ValidationError

from app.models.openai_protocol import (
    OpenAIChatMessage,
    OpenAIChatRequest,
)
from app.models.provider_execution import ProviderMessageRole
from app.providers.fake_openai_compatible_transport import (
    FakeOpenAICompatibleTransport,
)
from app.providers.transport import (
    TransportError,
    TransportRequest,
)
from app.services.openai_protocol_validator import (
    OpenAIProtocolValidationError,
    OpenAIProtocolValidator,
)


def protocol_request() -> OpenAIChatRequest:
    return OpenAIChatRequest(
        model="test-model",
        messages=[
            OpenAIChatMessage(
                role=ProviderMessageRole.USER,
                content="Hello",
            )
        ],
        stream=False,
    )


async def collect_stream(
    transport: FakeOpenAICompatibleTransport,
    request: TransportRequest,
) -> list[bytes]:
    return [chunk async for chunk in transport.stream(request)]


def transport_request() -> TransportRequest:
    return TransportRequest(
        destination="chat/completions",
        payload=b'{"model":"test-model"}',
    )


def test_protocol_models_have_deterministic_defaults_and_serialization() -> None:
    first = protocol_request()
    second = protocol_request()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.messages[0].name is None
    assert first.messages[0].tool_call_id is None
    assert first.temperature is None
    assert first.max_tokens is None


def test_protocol_models_are_immutable() -> None:
    request = protocol_request()

    with pytest.raises(ValidationError):
        request.model = "changed"


def test_validator_accepts_valid_request_and_response() -> None:
    validator = OpenAIProtocolValidator()
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello",
                }
            }
        ]
    }

    assert validator.validate_request(protocol_request()).model == "test-model"
    assert (
        validator.validate_response(response)
        .choices[0]
        .message.content
        == "Hello"
    )


def test_validator_rejects_invalid_request_and_response() -> None:
    validator = OpenAIProtocolValidator()

    with pytest.raises(
        OpenAIProtocolValidationError,
        match="request",
    ):
        validator.validate_request({"messages": [], "stream": False})

    with pytest.raises(
        OpenAIProtocolValidationError,
        match="response",
    ):
        validator.validate_response({"choices": []})


def test_validator_accepts_valid_stream_chunk() -> None:
    chunk = OpenAIProtocolValidator().validate_stream_chunk(
        {
            "choices": [
                {
                    "delta": {"content": "Hello"},
                    "finish_reason": None,
                }
            ]
        }
    )

    assert chunk.choices[0].delta.content == "Hello"


def test_validator_rejects_invalid_stream_chunk() -> None:
    with pytest.raises(
        OpenAIProtocolValidationError,
        match="stream chunk",
    ):
        OpenAIProtocolValidator().validate_stream_chunk(
            {"choices": [{"finish_reason": None}]}
        )


def test_fake_protocol_transport_is_deterministic() -> None:
    transport = FakeOpenAICompatibleTransport()
    request = transport_request()

    first_response = asyncio.run(transport.send(request))
    second_response = asyncio.run(transport.send(request))
    first_stream = asyncio.run(collect_stream(transport, request))
    second_stream = asyncio.run(collect_stream(transport, request))

    assert first_response == second_response
    assert first_stream == second_stream


def test_fake_protocol_transport_supports_deterministic_errors() -> None:
    transport = FakeOpenAICompatibleTransport(
        error_message="Protocol transport failed."
    )

    with pytest.raises(TransportError, match="Protocol transport failed"):
        asyncio.run(transport.send(transport_request()))
