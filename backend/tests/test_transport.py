import asyncio

import pytest
from pydantic import ValidationError

from app.providers.fake_transport import (
    DEFAULT_FAKE_PAYLOAD,
    DEFAULT_FAKE_STREAM,
    FakeTransport,
)
from app.providers.transport import (
    Transport,
    TransportError,
    TransportRequest,
    TransportResponse,
)


def request(
    *,
    simulate_error: bool = False,
) -> TransportRequest:
    return TransportRequest(
        destination="provider-protocol",
        payload=b'{"request":true}',
        metadata={"simulate_error": simulate_error},
    )


async def collect_stream(
    transport: Transport,
    transport_request: TransportRequest,
) -> list[bytes]:
    return [
        chunk
        async for chunk in transport.stream(transport_request)
    ]


def test_fake_transport_send_success() -> None:
    response = asyncio.run(FakeTransport().send(request()))

    assert response == TransportResponse(
        payload=DEFAULT_FAKE_PAYLOAD,
        metadata={
            "transport": "fake",
            "deterministic": True,
        },
    )


def test_fake_transport_stream_success() -> None:
    chunks = asyncio.run(collect_stream(FakeTransport(), request()))

    assert chunks == list(DEFAULT_FAKE_STREAM)


def test_fake_transport_output_is_deterministic() -> None:
    transport = FakeTransport()

    first_response = asyncio.run(transport.send(request()))
    second_response = asyncio.run(transport.send(request()))
    first_stream = asyncio.run(collect_stream(transport, request()))
    second_stream = asyncio.run(collect_stream(transport, request()))

    assert first_response == second_response
    assert first_response is not second_response
    assert first_stream == second_stream


def test_fake_transport_supports_configured_failure() -> None:
    metadata_failure = request(simulate_error=True)
    configured_failure = FakeTransport(error_message="Transport unavailable.")

    with pytest.raises(
        TransportError,
        match="Simulated fake transport failure",
    ):
        asyncio.run(FakeTransport().send(metadata_failure))

    with pytest.raises(TransportError, match="Transport unavailable"):
        asyncio.run(collect_stream(configured_failure, request()))


def test_transport_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Transport()


def test_transport_request_is_immutable_and_not_mutated() -> None:
    transport_request = request()
    before = transport_request.model_dump(mode="json")

    asyncio.run(FakeTransport().send(transport_request))

    assert transport_request.model_dump(mode="json") == before
    with pytest.raises(ValidationError):
        transport_request.destination = "changed"
