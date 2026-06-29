import asyncio
from collections.abc import AsyncIterator

import pytest

from app.providers.configured_transport import ConfiguredTransport
from app.providers.transport import (
    Transport,
    TransportRequest,
    TransportResponse,
)


class SpyTransport(Transport):
    def __init__(self) -> None:
        self.request: TransportRequest | None = None

    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        self.request = request
        return TransportResponse(payload=b"ok")

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self.request = request
        yield b"chunk"


def test_configured_transport_resolves_relative_destination() -> None:
    async def run() -> None:
        spy = SpyTransport()
        transport = ConfiguredTransport(
            transport=spy,
            base_url="https://example.test/v1",
        )

        response = await transport.send(
            TransportRequest(destination="chat/completions")
        )

        assert response.payload == b"ok"
        assert spy.request is not None
        assert spy.request.destination == (
            "https://example.test/v1/chat/completions"
        )

    asyncio.run(run())


def test_configured_transport_preserves_absolute_destination() -> None:
    async def run() -> None:
        spy = SpyTransport()
        transport = ConfiguredTransport(
            transport=spy,
            base_url="https://example.test/v1",
        )

        await transport.send(
            TransportRequest(destination="https://other.test/anything")
        )

        assert spy.request is not None
        assert spy.request.destination == "https://other.test/anything"

    asyncio.run(run())


def test_configured_transport_merges_headers_without_mutating_request() -> None:
    async def run() -> None:
        spy = SpyTransport()
        transport = ConfiguredTransport(
            transport=spy,
            base_url="https://example.test/v1",
            default_headers={
                "Authorization": "Bearer default",
                "Content-Type": "application/json",
            },
        )
        request = TransportRequest(
            destination="chat/completions",
            metadata={
                "headers": {
                    "Authorization": "Bearer override",
                    "X-Test": "yes",
                },
                "method": "POST",
            },
        )
        before = request.model_dump()

        await transport.send(request)

        assert request.model_dump() == before
        assert spy.request is not None
        assert spy.request.metadata["headers"] == {
            "Authorization": "Bearer override",
            "Content-Type": "application/json",
            "X-Test": "yes",
        }
        assert spy.request.metadata["method"] == "POST"

    asyncio.run(run())


def test_configured_transport_stream_uses_configured_request() -> None:
    async def run() -> None:
        spy = SpyTransport()
        transport = ConfiguredTransport(
            transport=spy,
            base_url="https://example.test/v1/",
        )

        chunks = [
            chunk
            async for chunk in transport.stream(
                TransportRequest(destination="/chat/completions")
            )
        ]

        assert chunks == [b"chunk"]
        assert spy.request is not None
        assert spy.request.destination == (
            "https://example.test/v1/chat/completions"
        )

    asyncio.run(run())


def test_configured_transport_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base_url must not be empty"):
        ConfiguredTransport(
            transport=SpyTransport(),
            base_url=" ",
        )
