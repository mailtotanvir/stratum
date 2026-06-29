from collections.abc import AsyncIterator, Iterable

from app.providers.transport import (
    Transport,
    TransportError,
    TransportRequest,
    TransportResponse,
)


DEFAULT_FAKE_PAYLOAD = b'{"fake":true}'
DEFAULT_FAKE_STREAM = (b'{"fake":', b"true}")
DEFAULT_FAKE_ERROR = "Simulated fake transport failure."


class FakeTransport(Transport):
    def __init__(
        self,
        *,
        response: TransportResponse | None = None,
        stream_chunks: Iterable[bytes] | None = None,
        error_message: str | None = None,
    ) -> None:
        self._response = response or TransportResponse(
            payload=DEFAULT_FAKE_PAYLOAD,
            metadata={
                "transport": "fake",
                "deterministic": True,
            },
        )
        self._stream_chunks = tuple(
            DEFAULT_FAKE_STREAM
            if stream_chunks is None
            else stream_chunks
        )
        self._error_message = error_message

    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        self._raise_if_configured(request)
        return self._response.model_copy(deep=True)

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self._raise_if_configured(request)
        for chunk in self._stream_chunks:
            yield chunk

    def _raise_if_configured(
        self,
        request: TransportRequest,
    ) -> None:
        error_message = self._error_message
        if request.metadata.get("simulate_error") is True:
            error_message = DEFAULT_FAKE_ERROR
        if error_message is not None:
            raise TransportError(error_message)
