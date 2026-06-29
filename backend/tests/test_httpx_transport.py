from __future__ import annotations

import asyncio

import httpx
import pytest

from app.providers.httpx_transport import HttpxTransport
from app.providers.transport import TransportError, TransportRequest


def make_request(**overrides):
    data = {
        "destination": "https://example.test/v1/chat/completions",
        "payload": b'{"model":"gpt-4o-mini","messages":[]}',
        "metadata": {
            "method": "POST",
            "headers": {
                "Authorization": "Bearer test",
                "Content-Type": "application/json",
            },
        },
    }
    data.update(overrides)
    return TransportRequest(**data)


def test_httpx_transport_send_success() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://example.test/v1/chat/completions"
            assert request.headers["authorization"] == "Bearer test"
            assert request.content == b'{"model":"gpt-4o-mini","messages":[]}'
            return httpx.Response(
                200,
                content=b'{"id":"resp_1","choices":[]}',
                headers={"x-test": "ok"},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        response = await transport.send(make_request())

        assert response.payload == b'{"id":"resp_1","choices":[]}'
        assert response.metadata["status_code"] == 200
        assert response.metadata["headers"]["x-test"] == "ok"

        await client.aclose()

    asyncio.run(run())


def test_httpx_transport_stream_success() -> None:
    async def run() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"data: one\n\ndata: two\n\n",
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        chunks = [chunk async for chunk in transport.stream(make_request())]

        assert b"".join(chunks) == b"data: one\n\ndata: two\n\n"

        await client.aclose()

    asyncio.run(run())


def test_httpx_transport_send_failure_translates_to_transport_error() -> None:
    async def run() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        with pytest.raises(TransportError, match="HTTP transport failed"):
            await transport.send(make_request())

        await client.aclose()

    asyncio.run(run())


def test_httpx_transport_stream_failure_translates_to_transport_error() -> None:
    async def run() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("stream boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        with pytest.raises(TransportError, match="HTTP stream transport failed"):
            _ = [chunk async for chunk in transport.stream(make_request())]

        await client.aclose()

    asyncio.run(run())


def test_httpx_transport_does_not_mutate_request() -> None:
    async def run() -> None:
        request = make_request()
        before = request.model_dump()

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b'{"ok":true}')

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        await transport.send(request)

        assert request.model_dump() == before

        await client.aclose()

    asyncio.run(run())


def test_httpx_transport_send_http_error_status_raises_transport_error() -> None:
    async def run() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                content=b'{"error":"invalid api key"}',
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        with pytest.raises(
            TransportError,
            match="HTTP transport failed with status 401",
        ):
            await transport.send(make_request())

        await client.aclose()

    asyncio.run(run())


def test_httpx_transport_stream_http_error_status_raises_transport_error() -> None:
    async def run() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                content=b'{"error":"rate limited"}',
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = HttpxTransport(client=client)

        with pytest.raises(
            TransportError,
            match="HTTP stream transport failed with status 429",
        ):
            _ = [chunk async for chunk in transport.stream(make_request())]

        await client.aclose()

    asyncio.run(run())
