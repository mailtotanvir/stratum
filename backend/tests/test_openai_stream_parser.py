import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.services.openai_stream_parser import (
    OpenAIStreamParser,
    OpenAIStreamParserError,
)


def request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="openai-compatible",
        model="request-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Stream a response.",
            )
        ],
        stream_mode=ProviderStreamMode.SSE,
    )


def chunk(
    delta: dict,
    *,
    finish_reason: str | None = None,
) -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl-stream",
            "model": "response-model",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        },
        sort_keys=True,
    ).encode()


async def bytes_iterator(*chunks: bytes) -> AsyncIterator[bytes]:
    for value in chunks:
        yield value


async def collect(*chunks: bytes):
    return [
        event
        async for event in OpenAIStreamParser().parse(
            bytes_iterator(*chunks),
            request(),
        )
    ]


def test_parses_ordered_assistant_and_empty_deltas() -> None:
    events = asyncio.run(
        collect(
            chunk({"role": "assistant"}),
            chunk({"content": "Hello"}),
            chunk({"content": ""}),
        )
    )

    assert [event.event_type for event in events] == [
        "delta",
        "delta",
        "delta",
    ]
    assert [event.content for event in events] == [None, "Hello", ""]
    assert [event.sequence for event in events] == [0, 1, 2]
    assert all(event.model == "response-model" for event in events)


def test_finish_event_completes_stream() -> None:
    events = asyncio.run(
        collect(
            chunk({"content": "Done"}),
            chunk({}, finish_reason="stop"),
            b"data: [DONE]\n\n",
        )
    )

    assert [event.event_type for event in events] == [
        "delta",
        "completed",
    ]
    assert events[-1].done is True
    assert events[-1].metadata == {
        "response_id": "chatcmpl-stream",
        "finish_reason": "stop",
    }


def test_done_marker_completes_unfinished_stream() -> None:
    events = asyncio.run(
        collect(
            b'data: {"choices":[{"delta":{"content":"A"},'
            b'"finish_reason":null}]}\n\n',
            b"data: [DONE]\n\n",
        )
    )

    assert [event.event_type for event in events] == [
        "delta",
        "completed",
    ]


def test_malformed_chunk_raises_parser_error() -> None:
    with pytest.raises(
        OpenAIStreamParserError,
        match="Malformed OpenAI-compatible stream chunk",
    ):
        asyncio.run(collect(b"not-json"))


def test_stream_output_is_deterministic() -> None:
    chunks = (
        chunk({"content": "Same"}),
        chunk({}, finish_reason="stop"),
    )

    first = asyncio.run(collect(*chunks))
    second = asyncio.run(collect(*chunks))

    assert [item.model_dump(mode="json") for item in first] == [
        item.model_dump(mode="json") for item in second
    ]


def test_parser_splits_multiple_sse_events_in_single_http_chunk() -> None:
    first = (
        b'data: {"choices":[{"delta":{"content":"A"},'
        b'"finish_reason":null}]}\n\n'
    )
    second = (
        b'data: {"choices":[{"delta":{"content":"B"},'
        b'"finish_reason":null}]}\n\n'
    )
    done = b"data: [DONE]\n\n"

    events = asyncio.run(collect(first + second + done))

    assert [event.event_type for event in events] == [
        "delta",
        "delta",
        "completed",
    ]
    assert [event.content for event in events] == ["A", "B", None]


def test_parser_buffers_partial_sse_events_across_http_chunks() -> None:
    events = asyncio.run(
        collect(
            b'data: {"choices":[{"delta":{"content":"Hel',
            b'lo"},"finish_reason":null}]}\n\n',
            b"data: [DONE]\n\n",
        )
    )

    assert [event.event_type for event in events] == [
        "delta",
        "completed",
    ]
    assert events[0].content == "Hello"


def test_parser_ignores_sse_comment_lines() -> None:
    events = asyncio.run(
        collect(
            b": keepalive\n\n",
            b'data: {"choices":[{"delta":{"content":"A"},'
            b'"finish_reason":null}]}\n\n',
            b"data: [DONE]\n\n",
        )
    )

    assert [event.event_type for event in events] == [
        "delta",
        "completed",
    ]
    assert events[0].content == "A"


def test_parser_ignores_extra_sse_data_after_done_marker() -> None:
    events = asyncio.run(
        collect(
            b'data: {"choices":[{"delta":{"content":"A"},'
            b'"finish_reason":null}]}\n\n',
            b"data: [DONE]\n\n",
            b'data: {"choices":[{"delta":{"content":"late"},'
            b'"finish_reason":null}]}\n\n',
        )
    )

    assert [event.event_type for event in events] == [
        "delta",
        "completed",
    ]
    assert [event.content for event in events] == ["A", None]
