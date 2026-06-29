import asyncio

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderExecutionStreamEvent,
    ProviderMessage,
    ProviderMessageRole,
)
from app.providers.base import ProviderAdapter, ProviderAdapterError
from app.providers.fake import (
    FAKE_RESPONSE_CONTENT,
    FakeProviderAdapter,
)


def request(
    *,
    simulate_error: bool = False,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="fake",
        model="fake-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Execute deterministic request",
            )
        ],
        metadata={"simulate_error": simulate_error},
    )


async def collect_stream(
    adapter: FakeProviderAdapter,
    execution_request: ProviderExecutionRequest,
) -> list[ProviderExecutionStreamEvent]:
    return [
        event
        async for event in adapter.stream(execution_request)
    ]


def test_fake_complete_success() -> None:
    result = asyncio.run(FakeProviderAdapter().complete(request()))

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == FAKE_RESPONSE_CONTENT
    assert result.latency_ms == 0
    assert result.raw_response == {
        "fake": True,
        "content": FAKE_RESPONSE_CONTENT,
    }


def test_fake_complete_includes_provider_and_model_metadata() -> None:
    result = asyncio.run(FakeProviderAdapter().complete(request()))

    assert result.provider == "fake"
    assert result.model == "fake-model"
    assert result.metadata == {
        "provider_id": "fake",
        "model": "fake-model",
        "deterministic": True,
    }
    assert result.usage is not None
    assert result.usage.total_tokens == 6


def test_fake_stream_yields_deterministic_ordered_events() -> None:
    adapter = FakeProviderAdapter()

    first = asyncio.run(collect_stream(adapter, request()))
    second = asyncio.run(collect_stream(adapter, request()))

    assert first == second
    assert [event.event_type for event in first] == [
        "start",
        "delta",
        "completed",
    ]
    assert [event.sequence for event in first] == [0, 1, 2]
    assert [event.content for event in first] == [
        None,
        FAKE_RESPONSE_CONTENT,
        None,
    ]
    assert [event.done for event in first] == [False, False, True]
    assert all(event.provider == "fake" for event in first)
    assert all(event.model == "fake-model" for event in first)


def test_fake_simulated_failure_raises_adapter_error() -> None:
    adapter = FakeProviderAdapter()
    failing_request = request(simulate_error=True)

    with pytest.raises(
        ProviderAdapterError,
        match="Simulated fake provider failure",
    ):
        asyncio.run(adapter.complete(failing_request))

    with pytest.raises(
        ProviderAdapterError,
        match="Simulated fake provider failure",
    ):
        asyncio.run(collect_stream(adapter, failing_request))


def test_provider_adapter_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        ProviderAdapter()
