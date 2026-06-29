import asyncio

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
)
from app.models.provider_execution_events import (
    ProviderExecutionCancelledEvent,
)
from app.providers.base import ProviderAdapterError
from app.providers.fake import FakeProviderAdapter
from app.runtime.python_async_runtime import PythonAsyncRuntime
from app.services.event_service import EventService
from app.services.provider_adapter_registry_service import (
    ProviderAdapterRegistryService,
)
from app.services.provider_execution_event_factory import (
    ProviderExecutionEventFactory,
)
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
                content="Cancellation contract request",
            )
        ],
        correlation_id="cancel-correlation",
    )


def test_cancelled_payload_validates_required_fields() -> None:
    event = ProviderExecutionCancelledEvent(
        provider_id="fake",
        model="fake-model",
        execution_id="execution-1",
        correlation_id="cancel-correlation",
        reason="caller_requested",
    )

    assert event.event_type == "provider_execution_cancelled"
    assert event.provider_id == "fake"
    assert event.model == "fake-model"
    assert event.execution_id == "execution-1"
    assert event.reason == "caller_requested"


def test_cancelled_payload_metadata_is_not_shared() -> None:
    first = ProviderExecutionCancelledEvent(
        provider_id="fake",
        model="fake-model",
        execution_id="execution-1",
        reason="caller_requested",
    )
    second = ProviderExecutionCancelledEvent(
        provider_id="fake",
        model="fake-model",
        execution_id="execution-2",
        reason="caller_requested",
    )

    first.metadata["source"] = "first"

    assert first.metadata == {"source": "first"}
    assert second.metadata == {}


def test_fake_adapter_cancel_succeeds_deterministically() -> None:
    adapter = FakeProviderAdapter()

    first = asyncio.run(adapter.cancel("execution-1"))
    second = asyncio.run(adapter.cancel("execution-1"))

    assert first is None
    assert second is None


class RecordingCancellationAdapter(FakeProviderAdapter):
    provider_id = "recording"

    def __init__(self) -> None:
        self.execution_ids: list[str] = []

    async def cancel(self, execution_id: str) -> None:
        self.execution_ids.append(execution_id)


def test_provider_execution_service_delegates_cancel() -> None:
    adapter = RecordingCancellationAdapter()
    service = ProviderExecutionService(
        adapter_registry=ProviderAdapterRegistryService([adapter])
    )

    result = asyncio.run(
        service.cancel("recording", "execution-1")
    )

    assert result is None
    assert adapter.execution_ids == ["execution-1"]


def test_unknown_provider_cancel_raises_registry_error() -> None:
    with pytest.raises(
        ValueError,
        match="Provider adapter is not registered: missing",
    ):
        asyncio.run(
            ProviderExecutionService().cancel(
                "missing",
                "execution-1",
            )
        )


class FailingCancellationAdapter(FakeProviderAdapter):
    provider_id = "failing-cancel"

    async def cancel(self, execution_id: str) -> None:
        raise ProviderAdapterError(
            f"Cancellation failed: {execution_id}"
        )


def test_adapter_cancellation_failure_propagates_unchanged() -> None:
    expected_adapter = FailingCancellationAdapter()
    service = ProviderExecutionService(
        adapter_registry=ProviderAdapterRegistryService(
            [expected_adapter]
        )
    )

    with pytest.raises(
        ProviderAdapterError,
        match="Cancellation failed: execution-1",
    ):
        asyncio.run(
            service.cancel("failing-cancel", "execution-1")
        )


def test_event_factory_builds_cancelled_runtime_event() -> None:
    event = ProviderExecutionEventFactory().build_cancelled(
        event_id=41,
        timestamp="2026-06-28T12:00:00+00:00",
        provider_id="fake",
        model="fake-model",
        execution_id="execution-1",
        reason="caller_requested",
        correlation_id="cancel-correlation",
        metadata={"source": "test"},
    )

    assert event.id == 41
    assert event.ts == "2026-06-28T12:00:00+00:00"
    assert event.type.value == "provider_execution_cancelled"
    assert event.message == "Provider execution cancelled"
    assert event.metadata["provider_id"] == "fake"
    assert event.metadata["model"] == "fake-model"
    assert event.metadata["execution_id"] == "execution-1"
    assert event.metadata["reason"] == "caller_requested"


def test_runtime_helper_does_not_emit_cancellation_event(tmp_path) -> None:
    events = EventService(
        TraceService(tmp_path / "no-runtime-cancellation.db")
    )
    runtime = PythonAsyncRuntime(
        events=events,
        provider_execution=ProviderExecutionService(),
    )

    asyncio.run(runtime._execute_provider_request(request()))

    assert "provider_execution_cancelled" not in [
        event.type.value
        for event in events.list_persisted_events()
    ]
