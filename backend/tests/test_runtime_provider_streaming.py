import asyncio

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStreamEvent,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.providers.base import ProviderAdapterError
from app.runtime.python_async_runtime import PythonAsyncRuntime
from app.services.event_service import EventService
from app.services.provider_execution_service import ProviderExecutionService
from app.services.trace_service import TraceService


def request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="fake",
        model="fake-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Stream through runtime boundary",
            )
        ],
        stream_mode=ProviderStreamMode.CHUNKED,
        correlation_id="stream-correlation",
        metadata={"source": "runtime-stream-test"},
    )


def event_service(tmp_path) -> EventService:
    return EventService(
        TraceService(tmp_path / "runtime-provider-stream.db")
    )


async def collect_stream(
    runtime: PythonAsyncRuntime,
    execution_request: ProviderExecutionRequest,
) -> list[ProviderExecutionStreamEvent]:
    return [
        event
        async for event in runtime._stream_provider_request(
            execution_request
        )
    ]


def event_types(events: EventService) -> list[str]:
    return [
        event.type.value
        for event in events.list_persisted_events()
    ]


def test_success_emits_stream_lifecycle_in_order(tmp_path) -> None:
    events = event_service(tmp_path)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=ProviderExecutionService(),
    )

    asyncio.run(collect_stream(runtime, request()))

    assert event_types(events) == [
        "provider_execution_stream_started",
        "provider_execution_stream_delta",
        "provider_execution_stream_completed",
    ]


def test_delta_events_preserve_adapter_order(tmp_path) -> None:
    events = event_service(tmp_path)
    output = [
        ProviderExecutionStreamEvent(
            provider="fake",
            model="fake-model",
            event_type="delta",
            sequence=1,
            content="first",
        ),
        ProviderExecutionStreamEvent(
            provider="fake",
            model="fake-model",
            event_type="delta",
            sequence=2,
            content="second",
        ),
    ]
    execution = StubStreamingExecutionService(output=output)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=execution,
    )

    yielded = asyncio.run(collect_stream(runtime, request()))
    deltas = events.list_persisted_events(
        event_type="provider_execution_stream_delta"
    )

    assert yielded[0] is output[0]
    assert yielded[1] is output[1]
    assert [event.metadata["content"] for event in deltas] == [
        "first",
        "second",
    ]
    assert [event.metadata["sequence"] for event in deltas] == [1, 2]


class StubStreamingExecutionService:
    def __init__(
        self,
        output: list[ProviderExecutionStreamEvent] | None = None,
        error: ProviderAdapterError | None = None,
    ) -> None:
        self.output = output or []
        self.error = error
        self.stream_calls = 0
        self.requests: list[ProviderExecutionRequest] = []

    async def stream(self, execution_request: ProviderExecutionRequest):
        self.stream_calls += 1
        self.requests.append(execution_request)
        if self.error is not None:
            raise self.error
        for event in self.output:
            yield event


def test_failure_emits_started_then_failed_and_re_raises(tmp_path) -> None:
    events = event_service(tmp_path)
    expected = ProviderAdapterError("stream adapter failure")
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=StubStreamingExecutionService(error=expected),
    )

    with pytest.raises(ProviderAdapterError) as caught:
        asyncio.run(collect_stream(runtime, request()))

    assert caught.value is expected
    assert event_types(events) == [
        "provider_execution_stream_started",
        "provider_execution_stream_failed",
    ]
    assert "provider_execution_stream_completed" not in event_types(events)


def test_stream_request_is_not_mutated(tmp_path) -> None:
    events = event_service(tmp_path)
    execution_request = request()
    before = execution_request.model_dump(mode="json")
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=ProviderExecutionService(),
    )

    asyncio.run(collect_stream(runtime, execution_request))

    assert execution_request.model_dump(mode="json") == before


def test_stream_helper_is_lazy(tmp_path) -> None:
    events = event_service(tmp_path)
    execution = StubStreamingExecutionService()
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=execution,
    )

    stream = runtime._stream_provider_request(request())

    assert execution.stream_calls == 0
    assert events.list_persisted_events() == []
    asyncio.run(stream.aclose())


def test_injected_execution_service_is_respected(tmp_path) -> None:
    events = event_service(tmp_path)
    output = [
        ProviderExecutionStreamEvent(
            provider="custom",
            model="fake-model",
            event_type="delta",
            sequence=4,
            content="injected",
        )
    ]
    execution = StubStreamingExecutionService(output=output)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=execution,
    )
    execution_request = request()

    yielded = asyncio.run(
        collect_stream(runtime, execution_request)
    )

    assert execution.stream_calls == 1
    assert execution.requests == [execution_request]
    assert yielded[0] is output[0]


def test_stream_event_payloads_preserve_identity(tmp_path) -> None:
    events = event_service(tmp_path)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=ProviderExecutionService(),
    )

    asyncio.run(collect_stream(runtime, request()))
    persisted = events.list_persisted_events()

    execution_ids = {
        event.metadata["execution_id"]
        for event in persisted
    }
    assert len(execution_ids) == 1
    assert all(
        event.metadata["provider_id"] == "fake"
        for event in persisted
    )
    assert all(
        event.metadata["model"] == "fake-model"
        for event in persisted
    )
    assert all(
        event.metadata["correlation_id"] == "stream-correlation"
        for event in persisted
    )


def test_streaming_event_order_is_deterministic(tmp_path) -> None:
    events = event_service(tmp_path)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=ProviderExecutionService(),
    )

    first = asyncio.run(collect_stream(runtime, request()))
    second = asyncio.run(collect_stream(runtime, request()))
    persisted = events.list_persisted_events()

    assert first == second
    assert [event.type.value for event in persisted[:3]] == [
        event.type.value for event in persisted[3:]
    ]
    assert [
        event.metadata for event in persisted[:3]
    ] == [
        event.metadata for event in persisted[3:]
    ]
