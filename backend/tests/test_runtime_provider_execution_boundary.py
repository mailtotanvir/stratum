import asyncio

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
)
from app.providers.base import ProviderAdapterError
from app.runtime.python_async_runtime import PythonAsyncRuntime
from app.services.provider_execution_service import (
    provider_execution_service,
)


def request(provider: str = "fake") -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model="fake-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Execute through runtime boundary",
            )
        ],
        metadata={"source": "runtime-boundary-test"},
    )


class RecordingProviderExecutionService:
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


def completed_result() -> ProviderExecutionResult:
    return ProviderExecutionResult(
        status=ProviderExecutionStatus.COMPLETED,
        provider="fake",
        model="fake-model",
        content="Boundary response.",
    )


def test_runtime_delegates_to_provider_execution_service() -> None:
    execution = RecordingProviderExecutionService(completed_result())
    runtime = PythonAsyncRuntime(provider_execution=execution)
    execution_request = request()

    asyncio.run(runtime._execute_provider_request(execution_request))

    assert execution.requests == [execution_request]
    assert execution.requests[0] is execution_request


def test_provider_request_reaches_boundary_unchanged() -> None:
    execution = RecordingProviderExecutionService(completed_result())
    runtime = PythonAsyncRuntime(provider_execution=execution)
    execution_request = request()
    before = execution_request.model_dump(mode="json")

    asyncio.run(runtime._execute_provider_request(execution_request))

    assert execution_request.model_dump(mode="json") == before


def test_provider_result_is_returned_unchanged() -> None:
    expected = completed_result()
    execution = RecordingProviderExecutionService(expected)
    runtime = PythonAsyncRuntime(provider_execution=execution)

    result = asyncio.run(runtime._execute_provider_request(request()))

    assert result is expected


def test_injected_provider_execution_service_is_used() -> None:
    expected = completed_result()
    execution = RecordingProviderExecutionService(expected)
    runtime = PythonAsyncRuntime(provider_execution=execution)

    result = asyncio.run(runtime._execute_provider_request(request()))

    assert runtime._provider_execution is execution
    assert result.content == "Boundary response."


def test_provider_adapter_error_propagates_unchanged() -> None:
    expected_error = ProviderAdapterError("boundary adapter failure")
    execution = RecordingProviderExecutionService(error=expected_error)
    runtime = PythonAsyncRuntime(provider_execution=execution)

    with pytest.raises(
        ProviderAdapterError,
        match="boundary adapter failure",
    ) as caught:
        asyncio.run(runtime._execute_provider_request(request()))

    assert caught.value is expected_error


def test_unknown_provider_error_propagates() -> None:
    runtime = PythonAsyncRuntime()

    with pytest.raises(
        ValueError,
        match="Provider adapter is not registered: missing",
    ):
        asyncio.run(
            runtime._execute_provider_request(request(provider="missing"))
        )


def test_default_runtime_uses_existing_provider_execution_service() -> None:
    runtime = PythonAsyncRuntime()

    assert runtime._provider_execution is provider_execution_service


def test_existing_runtime_behavior_does_not_invoke_unused_boundary() -> None:
    execution = RecordingProviderExecutionService(completed_result())
    runtime = PythonAsyncRuntime(provider_execution=execution)

    assert runtime._governance_preview()["decision"] == "allow"
    assert execution.requests == []
