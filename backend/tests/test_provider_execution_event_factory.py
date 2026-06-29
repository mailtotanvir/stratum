from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderExecutionStreamEvent,
    ProviderMessage,
    ProviderMessageRole,
    ProviderUsage,
)
from app.providers.base import ProviderAdapterError
from app.services.provider_execution_event_factory import (
    ProviderExecutionEventFactory,
)


def request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="fake",
        model="fake-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Factory request content",
            )
        ],
        correlation_id="factory-correlation",
        metadata={"source": "factory-test"},
    )


def result() -> ProviderExecutionResult:
    return ProviderExecutionResult(
        status=ProviderExecutionStatus.COMPLETED,
        provider="fake",
        model="fake-model",
        content="Factory result.",
        usage=ProviderUsage(input_tokens=3, output_tokens=2),
        metadata={"finish_reason": "stop"},
    )


def test_execution_id_is_deterministic() -> None:
    factory = ProviderExecutionEventFactory()

    first = factory.execution_id(request())
    second = factory.execution_id(request())

    assert first == second
    assert first.startswith("provider-execution-")


def test_requested_payload_is_compact_and_stable() -> None:
    factory = ProviderExecutionEventFactory()
    execution_request = request()
    execution_id = factory.execution_id(execution_request)

    event = factory.create_requested(execution_request, execution_id)

    assert event.provider_id == "fake"
    assert event.model == "fake-model"
    assert event.execution_id == execution_id
    assert event.capability == "chat"
    assert event.metadata == {"source": "factory-test"}
    assert "messages" not in event.model_dump(mode="json")


def test_completed_payload_reuses_usage_and_result_metadata() -> None:
    factory = ProviderExecutionEventFactory()
    execution_request = request()

    event = factory.create_completed(
        execution_request,
        result(),
        factory.execution_id(execution_request),
    )

    assert event.usage is not None
    assert event.usage.total_tokens == 5
    assert event.result_metadata == {"finish_reason": "stop"}


def test_failed_payload_has_stable_error_fields() -> None:
    factory = ProviderExecutionEventFactory()
    execution_request = request()

    event = factory.create_failed(
        execution_request,
        ProviderAdapterError("factory failure"),
        factory.execution_id(execution_request),
    )

    assert event.error_type == "ProviderAdapterError"
    assert event.error_message == "factory failure"


def test_factory_does_not_mutate_request_or_result() -> None:
    factory = ProviderExecutionEventFactory()
    execution_request = request()
    execution_result = result()
    request_before = execution_request.model_dump(mode="json")
    result_before = execution_result.model_dump(mode="json")
    execution_id = factory.execution_id(execution_request)

    factory.create_requested(execution_request, execution_id)
    factory.create_completed(
        execution_request,
        execution_result,
        execution_id,
    )

    assert execution_request.model_dump(mode="json") == request_before
    assert execution_result.model_dump(mode="json") == result_before


def test_stream_factory_payloads_preserve_identity_and_sequence() -> None:
    factory = ProviderExecutionEventFactory()
    execution_request = request()
    execution_id = factory.execution_id(execution_request)
    stream_event = ProviderExecutionStreamEvent(
        provider="fake",
        model="fake-model",
        event_type="delta",
        sequence=3,
        content="delta",
        metadata={"chunk": True},
    )

    started = factory.create_stream_started(
        execution_request,
        execution_id,
    )
    delta = factory.create_stream_delta(
        execution_request,
        stream_event,
        execution_id,
    )
    completed = factory.create_stream_completed(
        execution_request,
        execution_id,
        sequence=4,
    )

    assert started.sequence == 0
    assert delta.sequence == 3
    assert delta.content == "delta"
    assert delta.metadata == {
        "source": "factory-test",
        "chunk": True,
    }
    assert completed.sequence == 4
    assert {
        started.execution_id,
        delta.execution_id,
        completed.execution_id,
    } == {execution_id}
