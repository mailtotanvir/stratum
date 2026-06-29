import asyncio

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
    ProviderUsage,
)
from app.providers.base import ProviderAdapterError
from app.runtime.python_async_runtime import PythonAsyncRuntime
from app.services.event_service import EventService
from app.services.provider_execution_service import (
    ProviderExecutionService,
)
from app.services.trace_service import TraceService


def request(provider: str = "fake") -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model="fake-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Runtime provider event request",
            )
        ],
        correlation_id="runtime-event-correlation",
        metadata={"source": "runtime-event-test"},
    )


def completed_result() -> ProviderExecutionResult:
    return ProviderExecutionResult(
        status=ProviderExecutionStatus.COMPLETED,
        provider="fake",
        model="fake-model",
        content="Runtime provider result.",
        usage=ProviderUsage(input_tokens=4, output_tokens=3),
        metadata={"finish_reason": "stop"},
    )


class StubProviderExecutionService:
    def __init__(
        self,
        result: ProviderExecutionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests: list[ProviderExecutionRequest] = []

    async def complete(
        self,
        execution_request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        self.requests.append(execution_request)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def event_service(tmp_path) -> EventService:
    return EventService(
        TraceService(tmp_path / "runtime-provider-events.db")
    )


def event_types(events: EventService) -> list[str]:
    return [
        event.type.value
        for event in events.list_persisted_events()
    ]


def test_success_emits_requested_then_completed(tmp_path) -> None:
    events = event_service(tmp_path)
    execution = StubProviderExecutionService(completed_result())
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=execution,
    )

    asyncio.run(runtime._execute_provider_request(request()))

    assert event_types(events) == [
        "provider_execution_requested",
        "provider_execution_completed",
    ]


def test_adapter_failure_emits_requested_then_failed(tmp_path) -> None:
    events = event_service(tmp_path)
    execution = StubProviderExecutionService(
        error=ProviderAdapterError("simulated adapter failure")
    )
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=execution,
    )

    with pytest.raises(ProviderAdapterError):
        asyncio.run(runtime._execute_provider_request(request()))

    assert event_types(events) == [
        "provider_execution_requested",
        "provider_execution_failed",
    ]


def test_original_adapter_error_is_re_raised(tmp_path) -> None:
    events = event_service(tmp_path)
    expected = ProviderAdapterError("original adapter error")
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=StubProviderExecutionService(error=expected),
    )

    with pytest.raises(ProviderAdapterError) as caught:
        asyncio.run(runtime._execute_provider_request(request()))

    assert caught.value is expected


def test_unknown_provider_emits_failed_and_re_raises(tmp_path) -> None:
    events = event_service(tmp_path)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=ProviderExecutionService(),
    )

    with pytest.raises(
        ValueError,
        match="Provider adapter is not registered: missing",
    ) as caught:
        asyncio.run(
            runtime._execute_provider_request(request(provider="missing"))
        )

    assert type(caught.value) is ValueError
    assert event_types(events) == [
        "provider_execution_requested",
        "provider_execution_failed",
    ]


def test_result_and_request_are_not_mutated(tmp_path) -> None:
    events = event_service(tmp_path)
    expected_result = completed_result()
    execution_request = request()
    request_before = execution_request.model_dump(mode="json")
    result_before = expected_result.model_dump(mode="json")
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=StubProviderExecutionService(expected_result),
    )

    result = asyncio.run(
        runtime._execute_provider_request(execution_request)
    )

    assert result is expected_result
    assert execution_request.model_dump(mode="json") == request_before
    assert expected_result.model_dump(mode="json") == result_before


def test_event_payloads_include_stable_execution_identity(tmp_path) -> None:
    events = event_service(tmp_path)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=StubProviderExecutionService(
            completed_result()
        ),
    )

    asyncio.run(runtime._execute_provider_request(request()))
    requested, completed = events.list_persisted_events()

    assert requested.metadata["provider_id"] == "fake"
    assert requested.metadata["model"] == "fake-model"
    assert requested.metadata["execution_id"].startswith(
        "provider-execution-"
    )
    assert requested.metadata["execution_id"] == (
        completed.metadata["execution_id"]
    )
    assert requested.metadata["capability"] == "chat"
    assert completed.metadata["result_metadata"] == {
        "finish_reason": "stop"
    }
    assert completed.metadata["usage"]["total_tokens"] == 7


def test_no_event_is_emitted_after_failed_event(tmp_path) -> None:
    events = event_service(tmp_path)
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=StubProviderExecutionService(
            error=ProviderAdapterError("stop after failure")
        ),
    )

    with pytest.raises(ProviderAdapterError):
        asyncio.run(runtime._execute_provider_request(request()))

    persisted = events.list_persisted_events()
    assert len(persisted) == 2
    assert persisted[-1].type.value == "provider_execution_failed"


def test_unused_helper_emits_no_provider_events(tmp_path) -> None:
    events = event_service(tmp_path)

    PythonAsyncRuntime(
        events=events,
        provider_execution=StubProviderExecutionService(
            completed_result()
        ),
    )

    assert events.list_persisted_events() == []
