from collections.abc import AsyncIterator
from urllib.parse import urljoin

from app.providers.transport import (
    Transport,
    TransportRequest,
    TransportResponse,
)


class ConfiguredTransport(Transport):
    """Transport decorator that applies endpoint configuration.

    It keeps protocol adapters free from concrete provider endpoint details:
    - resolves relative destinations against base_url
    - merges default headers
    - preserves request metadata without mutation
    """

    def __init__(
        self,
        *,
        transport: Transport,
        base_url: str,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._transport = transport
        self._base_url = _normalize_base_url(base_url)
        self._default_headers = dict(default_headers or {})

    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        return await self._transport.send(self._configure(request))

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        async for chunk in self._transport.stream(self._configure(request)):
            yield chunk

    def _configure(
        self,
        request: TransportRequest,
    ) -> TransportRequest:
        metadata = dict(request.metadata)
        headers = dict(self._default_headers)
        headers.update(dict(metadata.get("headers", {})))
        metadata["headers"] = headers

        return TransportRequest(
            destination=_resolve_destination(
                self._base_url,
                request.destination,
            ),
            payload=request.payload,
            metadata=metadata,
        )


def _normalize_base_url(base_url: str) -> str:
    stripped = base_url.strip()
    if not stripped:
        raise ValueError("base_url must not be empty")
    return stripped.rstrip("/") + "/"


def _resolve_destination(base_url: str, destination: str) -> str:
    stripped = destination.strip()
    if not stripped:
        raise ValueError("destination must not be empty")
    if stripped.startswith(("http://", "https://")):
        return stripped
    return urljoin(base_url, stripped.lstrip("/"))
