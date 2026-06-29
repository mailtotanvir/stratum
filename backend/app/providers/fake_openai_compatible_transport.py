import json
from collections.abc import AsyncIterator, Iterable
from copy import deepcopy

from app.providers.transport import (
    Transport,
    TransportError,
    TransportRequest,
    TransportResponse,
)


FAKE_OPENAI_CONTENT = "Fake OpenAI-compatible response."


class FakeOpenAICompatibleTransport(Transport):
    def __init__(
        self,
        *,
        response_body: dict | None = None,
        stream_chunks: Iterable[dict | bytes] | None = None,
        error_message: str | None = None,
        malformed_response: bool = False,
        malformed_stream: bool = False,
    ) -> None:
        self._response_body = deepcopy(response_body)
        self._stream_chunks = (
            None
            if stream_chunks is None
            else tuple(deepcopy(list(stream_chunks)))
        )
        self._error_message = error_message
        self._malformed_response = malformed_response
        self._malformed_stream = malformed_stream

    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        self._raise_if_configured()
        if self._malformed_response:
            return TransportResponse(payload=b'{"choices":[]}')
        body = self._response_body or _default_response(request)
        return TransportResponse(
            payload=_encode(body),
            metadata={
                "transport": "fake-openai-compatible",
                "deterministic": True,
            },
        )

    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        self._raise_if_configured()
        if self._malformed_stream:
            yield b"not-json"
            return
        chunks = self._stream_chunks or _default_stream(request)
        for chunk in chunks:
            if isinstance(chunk, bytes):
                yield chunk
            else:
                yield _encode(chunk)

    def _raise_if_configured(self) -> None:
        if self._error_message is not None:
            raise TransportError(self._error_message)


def _request_model(request: TransportRequest) -> str:
    try:
        payload = json.loads(request.payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "fake-model"
    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
        return payload["model"]
    return "fake-model"


def _default_response(request: TransportRequest) -> dict:
    return {
        "id": "chatcmpl-fake",
        "model": _request_model(request),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": FAKE_OPENAI_CONTENT,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
        },
    }


def _default_stream(request: TransportRequest) -> tuple[dict, ...]:
    model = _request_model(request)
    common = {
        "id": "chatcmpl-fake",
        "model": model,
    }
    return (
        {
            **common,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                }
            ],
        },
        {
            **common,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": FAKE_OPENAI_CONTENT},
                    "finish_reason": None,
                }
            ],
        },
        {
            **common,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        },
    )


def _encode(payload: dict) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
