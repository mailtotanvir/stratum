from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
)
from app.providers.mock_provider import MockProvider


def request(mode: ProviderExecutionMode) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="mock",
        model="mock-large",
        mode=mode,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Hello mock provider",
            )
        ],
    )


def test_execute_chat() -> None:
    result = MockProvider().execute(request(ProviderExecutionMode.CHAT))

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == "Mock response."


def test_execute_completion() -> None:
    result = MockProvider().execute(
        ProviderExecutionRequest(
            provider="mock",
            model="mock-small",
            mode=ProviderExecutionMode.COMPLETION,
            messages=[],
        )
    )

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == "Mock completion."


def test_execute_tool_call() -> None:
    result = MockProvider().execute(request(ProviderExecutionMode.TOOL_CALL))

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == "Mock tool call."


def test_deterministic_responses() -> None:
    provider = MockProvider()
    execution_request = request(ProviderExecutionMode.CHAT)

    first = provider.execute(execution_request)
    second = provider.execute(execution_request)

    assert first == second


def test_usage_populated() -> None:
    result = MockProvider().execute(request(ProviderExecutionMode.CHAT))

    assert result.usage is not None
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 2
    assert result.usage.total_tokens == 5
    assert result.usage.estimated_cost == 0


def test_raw_response_contains_mock_marker() -> None:
    result = MockProvider().execute(request(ProviderExecutionMode.CHAT))

    assert result.raw_response == {"mock": True}


def test_streaming_support() -> None:
    provider = MockProvider()

    assert provider.supports_streaming("mock-large") is True
    assert provider.supports_streaming("mock-small") is False
    assert provider.supports_streaming("missing") is False


def test_provider_metadata_correct() -> None:
    provider = MockProvider()
    result = provider.execute(request(ProviderExecutionMode.CHAT))

    assert provider.provider_name() == "mock"
    assert provider.supported_models() == ["mock-small", "mock-large"]
    assert result.provider == "mock"
    assert result.model == "mock-large"
    assert result.latency_ms == 1
    assert result.metadata == {"provider": "mock"}
