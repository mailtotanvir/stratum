from app.models.provider_capability import (
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.providers.base_provider import BaseProvider
from app.providers.provider_registry import ProviderRegistry
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
)
from app.services.provider_execution_service import ProviderExecutionService
from app.services.provider_execution_validator_service import (
    ProviderExecutionValidatorService,
)


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


def test_provider_exception_is_caught_and_converted_to_failed_record() -> None:
    service = ProviderExecutionService(
        provider_registry=ProviderRegistry([FailingProvider()]),
        validator=ProviderExecutionValidatorService(
            ProviderCapabilityRegistryService(
                models=[
                    ProviderModelDescriptor(
                        provider="failing",
                        model="failure-model",
                        capabilities=[ProviderModelCapability.CHAT],
                    )
                ]
            )
        ),
    )

    record = service.execute(
        request(provider="failing", model="failure-model")
    )

    assert record.status == ProviderExecutionStatus.FAILED
    assert record.result is not None
    assert record.result.error_message == "provider exploded"
    assert record.result.metadata == {"error_type": "RuntimeError"}


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
