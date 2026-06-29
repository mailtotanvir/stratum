from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.services.openai_request_builder import OpenAIRequestBuilder


def message(
    role: ProviderMessageRole,
    content: str,
    *,
    name: str | None = None,
    tool_call_id: str | None = None,
    metadata: dict | None = None,
) -> ProviderMessage:
    return ProviderMessage(
        role=role,
        content=content,
        name=name,
        tool_call_id=tool_call_id,
        metadata=metadata or {},
    )


def request(
    *,
    messages: list[ProviderMessage] | None = None,
    mode: ProviderExecutionMode = ProviderExecutionMode.CHAT,
    stream_mode: ProviderStreamMode = ProviderStreamMode.NONE,
    metadata: dict | None = None,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="openai-compatible",
        model="test-model",
        mode=mode,
        messages=(
            messages
            if messages is not None
            else [
                message(
                    ProviderMessageRole.USER,
                    "Hello provider",
                )
            ]
        ),
        stream_mode=stream_mode,
        metadata=metadata or {},
    )


def test_builds_minimal_request() -> None:
    built = OpenAIRequestBuilder().build(request())

    assert built.model == "test-model"
    assert len(built.messages) == 1
    assert built.messages[0].role == ProviderMessageRole.USER
    assert built.messages[0].content == "Hello provider"
    assert built.temperature is None
    assert built.max_tokens is None
    assert built.stream is False


def test_multi_message_request_preserves_order() -> None:
    execution_request = request(
        messages=[
            message(ProviderMessageRole.SYSTEM, "System context"),
            message(ProviderMessageRole.USER, "First question"),
            message(ProviderMessageRole.ASSISTANT, "First answer"),
            message(ProviderMessageRole.USER, "Second question"),
        ]
    )

    built = OpenAIRequestBuilder().build(execution_request)

    assert [
        item.role for item in built.messages
    ] == [
        ProviderMessageRole.SYSTEM,
        ProviderMessageRole.USER,
        ProviderMessageRole.ASSISTANT,
        ProviderMessageRole.USER,
    ]
    assert [item.content for item in built.messages] == [
        "System context",
        "First question",
        "First answer",
        "Second question",
    ]


def test_streaming_request_maps_stream_mode() -> None:
    sse = OpenAIRequestBuilder().build(
        request(stream_mode=ProviderStreamMode.SSE)
    )
    chunked = OpenAIRequestBuilder().build(
        request(stream_mode=ProviderStreamMode.CHUNKED)
    )

    assert sse.stream is True
    assert chunked.stream is True


def test_modeled_tool_message_fields_are_preserved_in_order() -> None:
    execution_request = request(
        mode=ProviderExecutionMode.TOOL_CALL,
        messages=[
            message(
                ProviderMessageRole.ASSISTANT,
                "Calling tool",
                name="assistant",
            ),
            message(
                ProviderMessageRole.TOOL,
                "Tool result",
                name="lookup",
                tool_call_id="call-1",
            ),
        ],
    )

    built = OpenAIRequestBuilder().build(execution_request)

    assert [
        item.model_dump(mode="json")
        for item in built.messages
    ] == [
        {
            "role": "assistant",
            "content": "Calling tool",
            "name": "assistant",
            "tool_call_id": None,
        },
        {
            "role": "tool",
            "content": "Tool result",
            "name": "lookup",
            "tool_call_id": "call-1",
        },
    ]


def test_temperature_and_max_tokens_are_preserved() -> None:
    execution_request = request().model_copy(
        update={
            "temperature": 0.4,
            "max_tokens": 128,
        },
        deep=True,
    )

    built = OpenAIRequestBuilder().build(execution_request)

    assert built.temperature == 0.4
    assert built.max_tokens == 128


def test_unsupported_metadata_is_ignored() -> None:
    execution_request = request(
        messages=[
            message(
                ProviderMessageRole.USER,
                "Metadata should not leak",
                metadata={"private": "message-value"},
            )
        ],
        metadata={
            "tools": [{"name": "unsupported"}],
            "response_format": {"type": "json_object"},
            "private": "request-value",
        },
    )

    dumped = OpenAIRequestBuilder().build(
        execution_request
    ).model_dump(mode="json")

    assert "metadata" not in dumped
    assert "tools" not in dumped
    assert "response_format" not in dumped
    assert "private" not in dumped["messages"][0]


def test_original_request_is_not_mutated() -> None:
    execution_request = request()
    before = execution_request.model_dump(mode="json")

    OpenAIRequestBuilder().build(execution_request)

    assert execution_request.model_dump(mode="json") == before


def test_model_dump_is_deterministic() -> None:
    builder = OpenAIRequestBuilder()
    execution_request = request(
        messages=[
            message(ProviderMessageRole.SYSTEM, "System"),
            message(ProviderMessageRole.USER, "User"),
        ]
    )

    first = builder.build(execution_request)
    second = builder.build(execution_request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first is not second
    assert first.messages is not second.messages


def test_empty_modeled_message_collection_is_preserved() -> None:
    execution_request = request(
        messages=[],
        mode=ProviderExecutionMode.COMPLETION,
    )

    built = OpenAIRequestBuilder().build(execution_request)

    assert built.messages == []
