from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.transport import (
    Transport,
    TransportError,
    TransportRequest,
    TransportResponse,
)


class HttpxTransport(Transport):
    """Protocol-agnostic HTTP transport.

    TransportRequest remains intentionally generic:
    - destination: URL
    - payload: raw bytes
    - metadata: method/headers/query/etc.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def send(self, request: TransportRequest) -> TransportResponse:
        try:
            async with self._client_context() as client:
                response = await client.request(
                    method=self._method(request),
                    url=request.destination,
                    headers=self._headers(request),
                    content=request.payload,
                    params=self._params(request),
                    timeout=self._timeout_seconds,
                )
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"HTTP transport failed: {exc}") from exc

        return TransportResponse(
            payload=response.content,
            metadata={
                "status_code": response.status_code,
                "headers": dict(response.headers),
            },
        )

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        try:
            async with self._client_context() as client:
                async with client.stream(
                    method=self._method(request),
                    url=request.destination,
                    headers=self._headers(request),
                    content=request.payload,
                    params=self._params(request),
                    timeout=self._timeout_seconds,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"HTTP stream transport failed: {exc}") from exc

    def _client_context(self) -> Any:
        if self._client is not None:
            return _BorrowedAsyncClient(self._client)
        return httpx.AsyncClient()

    @staticmethod
    def _method(request: TransportRequest) -> str:
        return str(request.metadata.get("method", "POST")).upper()

    @staticmethod
    def _headers(request: TransportRequest) -> dict[str, str]:
        return dict(request.metadata.get("headers", {}))

    @staticmethod
    def _params(request: TransportRequest) -> dict[str, str]:
        return dict(request.metadata.get("params", {}))


class _BorrowedAsyncClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_args: object) -> None:
        return None
