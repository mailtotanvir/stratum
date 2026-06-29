import asyncio

import pytest

from app.models.provider_capability import (
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.models.provider_configuration import ProviderConfiguration
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderExecutionStreamEvent,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.models.provider_routing import ProviderRoutingResult
from app.providers.base import ProviderAdapter, ProviderAdapterError
from app.providers.fake import FAKE_RESPONSE_CONTENT
from app.providers.base_provider import BaseProvider
from app.providers.provider_registry import ProviderRegistry
from app.services.event_service import EventService
from app.services.provider_adapter_registry_service import (
    ProviderAdapterRegistryService,
)
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


def message() -> ProviderMessage:
    return ProviderMessage(
        role=ProviderMessageRole.USER,
        content="Hello mock provider",
    )


def request(
    *,
    provider: str = "mock",
    model: str = "mock-large",
    mode: ProviderExecutionMode = ProviderExecutionMode.CHAT,
    stream_mode: ProviderStreamMode = ProviderStreamMode.NONE,
    max_tokens: int | None = None,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model=model,
        mode=mode,
        messages=[] if mode == ProviderExecutionMode.COMPLETION else [message()],
        stream_mode=stream_mode,
        max_tokens=max_tokens,
        runtime_session_id="session-1",
        task_id="task-1",
        correlation_id="correlation-1",
        metadata={"source": "test"},
    )


def test_valid_mock_chat_execution_returns_completed_record() -> None:
    record = ProviderExecutionService().execute(request())

    assert record.status == ProviderExecutionStatus.COMPLETED
    assert record.result is not None
    assert record.result.status == ProviderExecutionStatus.COMPLETED
    assert record.result.content == "Mock response."
    assert record.id.startswith("provider-execution-")


def test_valid_mock_completion_execution_returns_completed_record() -> None:
    record = ProviderExecutionService().execute(
        request(mode=ProviderExecutionMode.COMPLETION)
    )

    assert record.status == ProviderExecutionStatus.COMPLETED
    assert record.result is not None
    assert record.result.content == "Mock completion."


def test_validation_failure_returns_failed_record() -> None:
    record = ProviderExecutionService().execute(
        request(model="mock-small", stream_mode=ProviderStreamMode.SSE)
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.completed_at is not None
    assert record.result is not None
    assert record.result.status == ProviderExecutionStatus.FAILED
    assert "unsupported_streaming" in record.result.error_message


def test_unknown_provider_model_returns_failed_record() -> None:
    record = ProviderExecutionService().execute(
        request(provider="missing", model="missing")
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.result is not None
    assert "unknown_model" in record.result.error_message


class FailingProvider(BaseProvider):
    def provider_name(self) -> str:
        return "failing"

    def supported_models(self) -> list[str]:
        return ["failure-model"]

    def supports_streaming(self, model: str) -> bool:
        return False

    def execute(self, request: ProviderExecutionRequest):
        raise RuntimeError("provider exploded")


def configured_service(
    provider: BaseProvider,
    descriptor: ProviderModelDescriptor,
) -> ProviderExecutionService:
    registry = ProviderRegistry([provider])
    capabilities = ProviderCapabilityRegistryService([descriptor])
    configurations = ProviderConfigurationService(
        [
            ProviderConfiguration(
                provider_name=provider.provider_name(),
                display_name=provider.provider_name().title(),
                base_url="https://provider.example/v1",
                default_model=descriptor.model,
                enabled=True,
            )
        ]
    )
    return ProviderExecutionService(
        router=ProviderRouterService(
            configurations=configurations,
            adapters=registry,
            capabilities=capabilities,
        ),
        provider_registry=registry,
        validator=ProviderExecutionValidatorService(capabilities),
    )


def test_provider_exception_is_caught_and_converted_to_failed_record() -> None:
    service = configured_service(
        FailingProvider(),
        ProviderModelDescriptor(
            provider="failing",
            model="failure-model",
            capabilities=[ProviderModelCapability.CHAT],
        ),
    )

    record = service.execute(
        request(provider="failing", model="failure-model")
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.result is not None
    assert record.result.error_message == "provider exploded"
    assert record.result.metadata["error_type"] == "RuntimeError"
    assert record.result.metadata["routing"]["adapter_provider"] == "failing"


def test_record_copies_runtime_identity_fields() -> None:
    record = ProviderExecutionService().execute(request())

    assert record.runtime_session_id == "session-1"
    assert record.task_id == "task-1"
    assert record.correlation_id == "correlation-1"
    assert record.metadata["source"] == "test"


def test_record_contains_completed_at_after_execution() -> None:
    record = ProviderExecutionService().execute(request())

    assert record.completed_at is not None
    assert record.completed_at >= record.created_at


def test_validation_metadata_is_included_on_successful_record() -> None:
    record = ProviderExecutionService().execute(request())

    assert record.metadata["validation"] == {
        "provider": "mock",
        "model": "mock-large",
        "capabilities": [
            "chat",
            "completion",
            "tool_call",
            "streaming",
        ],
        "status": "available",
    }
    assert record.metadata["routing"] == {
        "requested_provider": "mock",
        "resolved_provider": "mock",
        "adapter_provider": "mock",
        "resolved_model": "mock-large",
    }


def test_failed_validation_metadata_includes_issues() -> None:
    record = ProviderExecutionService().execute(
        request(model="mock-small", stream_mode=ProviderStreamMode.SSE)
    )

    assert record.result is not None
    issues = record.result.metadata["validation_issues"]
    assert issues[0]["code"] == "unsupported_streaming"


def test_mock_large_streaming_request_succeeds() -> None:
    record = ProviderExecutionService().execute(
        request(model="mock-large", stream_mode=ProviderStreamMode.SSE)
    )

    assert record.status == ProviderExecutionStatus.COMPLETED


def test_mock_small_streaming_request_fails_validation() -> None:
    record = ProviderExecutionService().execute(
        request(model="mock-small", stream_mode=ProviderStreamMode.SSE)
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.result is not None
    assert "unsupported_streaming" in record.result.error_message


class FailedRouter:
    def resolve(
        self,
        provider: str,
        model: str | None = None,
    ) -> ProviderRoutingResult:
        return ProviderRoutingResult(
            resolved=False,
            error_message="Test routing failure.",
            metadata={
                "provider": provider,
                "model": model,
                "error_code": "test_routing_failure",
            },
        )


def test_router_failure_returns_failed_execution() -> None:
    record = ProviderExecutionService(
        router=FailedRouter(),
    ).execute(request())

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.result is not None
    assert record.result.error_message == "Test routing failure."
    assert record.result.metadata["routing_result"]["resolved"] is False
    assert record.metadata["routing_result"]["metadata"][
        "error_code"
    ] == "test_routing_failure"


class AliasProvider(BaseProvider):
    def provider_name(self) -> str:
        return "openai-compatible"

    def supported_models(self) -> list[str]:
        return []

    def supports_streaming(self, model: str) -> bool:
        return False

    def execute(
        self,
        request: ProviderExecutionRequest,
    ):
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content="Alias response.",
        )


def test_alias_provider_resolves_through_adapter() -> None:
    configurations = ProviderConfigurationService()
    configurations.update(
        configurations.get("openrouter").model_copy(
            update={"enabled": True},
            deep=True,
        )
    )
    registry = ProviderRegistry([AliasProvider()])
    service = ProviderExecutionService(
        router=ProviderRouterService(
            configurations=configurations,
            adapters=registry,
        ),
        provider_registry=registry,
    )

    record = service.execute(
        request(
            provider="openrouter",
            model="provider-routed",
        )
    )

    assert record.status == ProviderExecutionStatus.COMPLETED
    assert record.result is not None
    assert record.result.content == "Alias response."
    assert record.metadata["routing"] == {
        "requested_provider": "openrouter",
        "resolved_provider": "openrouter",
        "adapter_provider": "openai-compatible",
        "resolved_model": "provider-routed",
    }


class RouterMustNotRun:
    def resolve(self, provider: str, model: str | None = None):
        raise AssertionError("router must not run before validation succeeds")


def test_validator_executes_before_router() -> None:
    record = ProviderExecutionService(
        router=RouterMustNotRun(),
    ).execute(
        request(
            model="mock-small",
            stream_mode=ProviderStreamMode.SSE,
        )
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.result is not None
    assert "unsupported_streaming" in record.result.error_message


def test_runtime_events_include_resolved_provider(tmp_path) -> None:
    events = EventService(TraceService(tmp_path / "routing-events.db"))

    record = ProviderExecutionService(events=events).execute(request())

    assert record.status == ProviderExecutionStatus.COMPLETED
    completed = events.list_persisted_events()[-1]
    assert completed.metadata["requested_provider"] == "mock"
    assert completed.metadata["resolved_provider"] == "mock"
    assert completed.metadata["adapter_provider"] == "mock"
    for excluded_field in (
        "api_key",
        "headers",
        "configuration",
        "base_url",
        "timeout_seconds",
        "routing_result",
    ):
        assert excluded_field not in completed.metadata


async def collect_stream(
    service: ProviderExecutionService,
    execution_request: ProviderExecutionRequest,
) -> list[ProviderExecutionStreamEvent]:
    return [
        event
        async for event in service.stream(execution_request)
    ]


def fake_request(
    *,
    provider: str = "fake",
    simulate_error: bool = False,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model="fake-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[message()],
        metadata={"simulate_error": simulate_error},
    )


def test_async_complete_delegates_to_fake_adapter() -> None:
    result = asyncio.run(
        ProviderExecutionService().complete(fake_request())
    )

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == FAKE_RESPONSE_CONTENT


def test_async_complete_preserves_provider_id_and_model() -> None:
    execution_request = fake_request()

    result = asyncio.run(
        ProviderExecutionService().complete(execution_request)
    )

    assert execution_request.provider_id == "fake"
    assert result.provider == execution_request.provider_id
    assert result.model == execution_request.model


def test_async_stream_delegates_with_deterministic_events() -> None:
    service = ProviderExecutionService()

    first = asyncio.run(collect_stream(service, fake_request()))
    second = asyncio.run(collect_stream(service, fake_request()))

    assert first == second
    assert [event.event_type for event in first] == [
        "start",
        "delta",
        "completed",
    ]
    assert [event.sequence for event in first] == [0, 1, 2]


def test_async_unknown_provider_raises_registry_error() -> None:
    with pytest.raises(
        ValueError,
        match="Provider adapter is not registered: missing",
    ):
        asyncio.run(
            ProviderExecutionService().complete(
                fake_request(provider="missing")
            )
        )


def test_async_adapter_failure_propagates_unchanged() -> None:
    with pytest.raises(
        ProviderAdapterError,
        match="Simulated fake provider failure",
    ):
        asyncio.run(
            ProviderExecutionService().complete(
                fake_request(simulate_error=True)
            )
        )


def test_async_complete_does_not_mutate_request() -> None:
    execution_request = fake_request()
    before = execution_request.model_dump(mode="json")

    asyncio.run(
        ProviderExecutionService().complete(execution_request)
    )

    assert execution_request.model_dump(mode="json") == before


class CustomProviderAdapter(ProviderAdapter):
    provider_id = "custom"

    async def complete(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=self.provider_id,
            model=request.model,
            content="Custom response.",
        )

    async def stream(
        self,
        request: ProviderExecutionRequest,
    ):
        yield ProviderExecutionStreamEvent(
            provider=self.provider_id,
            model=request.model,
            event_type="completed",
            sequence=0,
            done=True,
        )


def test_custom_adapter_registry_can_be_injected() -> None:
    service = ProviderExecutionService(
        adapter_registry=ProviderAdapterRegistryService(
            [CustomProviderAdapter()]
        )
    )

    result = asyncio.run(
        service.complete(fake_request(provider="custom"))
    )

    assert result.provider == "custom"
    assert result.content == "Custom response."
