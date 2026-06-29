import json

from app.models.provider_execution_events import (
    ProviderExecutionCompletedEvent,
    ProviderExecutionFailedEvent,
    ProviderExecutionRequestedEvent,
    ProviderExecutionStreamCompletedEvent,
    ProviderExecutionStreamDeltaEvent,
    ProviderExecutionStreamFailedEvent,
    ProviderExecutionStreamStartedEvent,
)
from app.models.provider_capability import (
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.models.provider_configuration import ProviderConfiguration
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderUsage,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.providers.base_provider import BaseProvider
from app.providers.provider_registry import ProviderRegistry
from app.services.event_service import EventService
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)
from app.services.provider_execution_service import ProviderExecutionService
from app.services.provider_execution_validator_service import (
    ProviderExecutionValidatorService,
)
from app.services.provider_router_service import ProviderRouterService
from app.services.trace_service import TraceService


def request(
    *,
    provider: str = "mock",
    model: str = "mock-large",
    stream_mode: ProviderStreamMode = ProviderStreamMode.NONE,
    content: str = "Sensitive prompt content",
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model=model,
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=content,
            )
        ],
        stream_mode=stream_mode,
        runtime_session_id="session-1",
        task_id="task-1",
        correlation_id="correlation-1",
    )


def event_service(tmp_path) -> EventService:
    return EventService(
        TraceService(tmp_path / "provider-execution-events.db")
    )


def event_types(events: EventService) -> list[str]:
    return [
        event.type.value
        for event in events.list_persisted_events()
    ]


def test_valid_mock_execution_emits_requested_started_completed(
    tmp_path,
) -> None:
    events = event_service(tmp_path)

    record = ProviderExecutionService(events=events).execute(request())

    assert record.status == ProviderExecutionStatus.COMPLETED
    assert event_types(events) == [
        "provider_execution_requested",
        "provider_execution_started",
        "provider_execution_completed",
    ]


def test_validation_failure_emits_requested_validation_failed_failed(
    tmp_path,
) -> None:
    events = event_service(tmp_path)

    record = ProviderExecutionService(events=events).execute(
        request(model="mock-small", stream_mode=ProviderStreamMode.SSE)
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert event_types(events) == [
        "provider_execution_requested",
        "provider_execution_validation_failed",
        "provider_execution_failed",
    ]
    failed = events.list_persisted_events()[-1]
    assert failed.metadata["validation_issue_codes"] == [
        "unsupported_streaming"
    ]


class FailingProvider(BaseProvider):
    def provider_name(self) -> str:
        return "failing"

    def supported_models(self) -> list[str]:
        return ["failure-model"]

    def supports_streaming(self, model: str) -> bool:
        return False

    def execute(self, request: ProviderExecutionRequest):
        raise RuntimeError("provider exploded")


def test_adapter_exception_emits_requested_started_failed(tmp_path) -> None:
    events = event_service(tmp_path)
    registry = ProviderRegistry([FailingProvider()])
    capabilities = ProviderCapabilityRegistryService(
        models=[
            ProviderModelDescriptor(
                provider="failing",
                model="failure-model",
                capabilities=[ProviderModelCapability.CHAT],
            )
        ]
    )
    configurations = ProviderConfigurationService(
        [
            ProviderConfiguration(
                provider_name="failing",
                display_name="Failing",
                base_url="https://failing.example/v1",
                default_model="failure-model",
                enabled=True,
            )
        ]
    )
    service = ProviderExecutionService(
        router=ProviderRouterService(
            configurations=configurations,
            adapters=registry,
            capabilities=capabilities,
        ),
        provider_registry=registry,
        validator=ProviderExecutionValidatorService(capabilities),
        events=events,
    )

    record = service.execute(
        request(provider="failing", model="failure-model")
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert event_types(events) == [
        "provider_execution_requested",
        "provider_execution_started",
        "provider_execution_failed",
    ]
    failed = events.list_persisted_events()[-1]
    assert failed.metadata["error_type"] == "RuntimeError"
    assert failed.metadata["error_message"] == "provider exploded"


def test_event_payload_includes_safe_execution_metadata(tmp_path) -> None:
    events = event_service(tmp_path)

    record = ProviderExecutionService(events=events).execute(request())
    requested = events.list_persisted_events()[0]
    completed = events.list_persisted_events()[-1]

    assert requested.metadata == {
        "provider": "mock",
        "requested_provider": "mock",
        "model": "mock-large",
        "mode": "chat",
        "stream_mode": "none",
        "message_count": 1,
        "runtime_session_id": "session-1",
        "task_id": "task-1",
        "correlation_id": "correlation-1",
        "provider_execution_record_id": record.id,
        "status": "requested",
    }
    assert completed.metadata["status"] == "completed"
    assert completed.metadata["resolved_provider"] == "mock"
    assert completed.metadata["adapter_provider"] == "mock"
    assert completed.metadata["latency_ms"] == 1
    assert completed.metadata["usage"] == {
        "input_tokens": 3,
        "output_tokens": 2,
        "total_tokens": 5,
        "estimated_cost": 0.0,
        "currency": "USD",
    }


def test_event_payload_excludes_full_message_content(tmp_path) -> None:
    events = event_service(tmp_path)
    secret = "do-not-persist-this-prompt"

    ProviderExecutionService(events=events).execute(
        request(content=secret)
    )

    for event in events.list_persisted_events():
        serialized = json.dumps(event.metadata, sort_keys=True)
        assert secret not in serialized
        assert "messages" not in event.metadata
        assert "content" not in event.metadata


def test_service_works_without_event_dependency() -> None:
    record = ProviderExecutionService().execute(request())

    assert record.status == ProviderExecutionStatus.COMPLETED
    assert record.result is not None
    assert record.result.content == "Mock response."


def event_identity() -> dict[str, str]:
    return {
        "provider_id": "fake",
        "model": "fake-model",
        "execution_id": "execution-1",
    }


def test_requested_event_validates_execution_identity() -> None:
    event = ProviderExecutionRequestedEvent(
        **event_identity(),
        capability="chat",
    )

    assert event.provider_id == "fake"
    assert event.model == "fake-model"
    assert event.execution_id == "execution-1"
    assert event.capability == "chat"
    assert event.event_type == "provider_execution_requested"


def test_completed_event_supports_usage_and_result_metadata() -> None:
    event = ProviderExecutionCompletedEvent(
        **event_identity(),
        usage=ProviderUsage(
            input_tokens=4,
            output_tokens=2,
        ),
        result_metadata={"finish_reason": "stop"},
    )

    assert event.usage is not None
    assert event.usage.total_tokens == 6
    assert event.result_metadata == {"finish_reason": "stop"}


def test_failed_event_has_stable_error_information() -> None:
    event = ProviderExecutionFailedEvent(
        **event_identity(),
        error_type="ProviderAdapterError",
        error_message="Simulated provider failure.",
    )

    assert event.event_type == "provider_execution_failed"
    assert event.error_type == "ProviderAdapterError"
    assert event.error_message == "Simulated provider failure."


def test_stream_lifecycle_models_are_separate_and_ordered() -> None:
    events = [
        ProviderExecutionStreamStartedEvent(
            **event_identity(),
            sequence=0,
        ),
        ProviderExecutionStreamDeltaEvent(
            **event_identity(),
            sequence=1,
            content="Deterministic delta.",
        ),
        ProviderExecutionStreamCompletedEvent(
            **event_identity(),
            sequence=2,
            usage=ProviderUsage(total_tokens=3),
        ),
    ]
    failed = ProviderExecutionStreamFailedEvent(
        **event_identity(),
        sequence=2,
        error_type="ProviderAdapterError",
        error_message="Stream failed.",
    )

    assert [event.sequence for event in events] == [0, 1, 2]
    assert [event.event_type for event in events] == [
        "provider_execution_stream_started",
        "provider_execution_stream_delta",
        "provider_execution_stream_completed",
    ]
    assert failed.event_type == "provider_execution_stream_failed"
    assert failed.error_type == "ProviderAdapterError"


def test_event_metadata_defaults_are_not_shared() -> None:
    first = ProviderExecutionRequestedEvent(**event_identity())
    second = ProviderExecutionRequestedEvent(**event_identity())

    first.metadata["source"] = "first"

    assert first.metadata == {"source": "first"}
    assert second.metadata == {}


def test_event_models_serialize_deterministically() -> None:
    first = ProviderExecutionCompletedEvent(
        **event_identity(),
        capability="chat",
        usage=ProviderUsage(input_tokens=2, output_tokens=1),
        result_metadata={"finish_reason": "stop"},
        metadata={"source": "test"},
    )
    second = ProviderExecutionCompletedEvent(
        **event_identity(),
        capability="chat",
        usage=ProviderUsage(input_tokens=2, output_tokens=1),
        result_metadata={"finish_reason": "stop"},
        metadata={"source": "test"},
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
