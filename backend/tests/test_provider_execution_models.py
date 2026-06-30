from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRecord,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
    ProviderUsage,
)
from app.services.provider_budget_policy_service import (
    ProviderBudgetPolicyService,
)


def provider_message() -> ProviderMessage:
    return ProviderMessage(
        role=ProviderMessageRole.USER,
        content="Summarize the runtime state.",
    )


def test_valid_chat_request() -> None:
    request = ProviderExecutionRequest(
        provider="openai",
        model="gpt-test",
        mode=ProviderExecutionMode.CHAT,
        messages=[provider_message()],
        temperature=0.2,
        max_tokens=256,
        stream_mode=ProviderStreamMode.SSE,
        runtime_session_id="session-1",
        task_id="task-1",
        correlation_id="correlation-1",
    )

    assert request.provider == "openai"
    assert request.model == "gpt-test"
    assert request.messages[0].role == ProviderMessageRole.USER
    assert request.stream_mode == ProviderStreamMode.SSE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", ""),
        ("provider", "   "),
        ("model", ""),
        ("model", "   "),
    ],
)
def test_invalid_empty_provider_or_model(field: str, value: str) -> None:
    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "mode": ProviderExecutionMode.CHAT,
        "messages": [provider_message()],
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ProviderExecutionRequest(**payload)


def test_invalid_empty_messages_for_chat() -> None:
    with pytest.raises(ValidationError):
        ProviderExecutionRequest(
            provider="openai",
            model="gpt-test",
            mode=ProviderExecutionMode.CHAT,
            messages=[],
        )


def test_valid_completion_request_allows_empty_messages() -> None:
    request = ProviderExecutionRequest(
        provider="openai",
        model="gpt-test",
        mode=ProviderExecutionMode.COMPLETION,
        messages=[],
    )

    assert request.messages == []


@pytest.mark.parametrize("temperature", [0, 1, 2])
def test_temperature_bounds_accept_valid_values(temperature: float) -> None:
    request = ProviderExecutionRequest(
        provider="openai",
        model="gpt-test",
        mode=ProviderExecutionMode.CHAT,
        messages=[provider_message()],
        temperature=temperature,
    )

    assert request.temperature == temperature


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_temperature_bounds_reject_invalid_values(temperature: float) -> None:
    with pytest.raises(ValidationError):
        ProviderExecutionRequest(
            provider="openai",
            model="gpt-test",
            mode=ProviderExecutionMode.CHAT,
            messages=[provider_message()],
            temperature=temperature,
        )


def test_max_tokens_validation() -> None:
    valid = ProviderExecutionRequest(
        provider="openai",
        model="gpt-test",
        mode=ProviderExecutionMode.CHAT,
        messages=[provider_message()],
        max_tokens=1,
    )

    assert valid.max_tokens == 1
    with pytest.raises(ValidationError):
        ProviderExecutionRequest(
            provider="openai",
            model="gpt-test",
            mode=ProviderExecutionMode.CHAT,
            messages=[provider_message()],
            max_tokens=0,
        )


def test_usage_total_token_derivation() -> None:
    usage = ProviderUsage(input_tokens=11, output_tokens=17)

    assert usage.total_tokens == 28


def test_failed_result_requires_error_message() -> None:
    with pytest.raises(ValidationError):
        ProviderExecutionResult(
            status=ProviderExecutionStatus.FAILED,
            provider="openai",
            model="gpt-test",
        )

    failed = ProviderExecutionResult(
        status=ProviderExecutionStatus.FAILED,
        provider="openai",
        model="gpt-test",
        error_message="provider timeout",
    )
    assert failed.error_message == "provider timeout"


def test_provider_execution_record_creation() -> None:
    request = ProviderExecutionRequest(
        provider="openai",
        model="gpt-test",
        mode=ProviderExecutionMode.CHAT,
        messages=[provider_message()],
        runtime_session_id="session-1",
        task_id="task-1",
        correlation_id="correlation-1",
    )
    result = ProviderExecutionResult(
        status=ProviderExecutionStatus.COMPLETED,
        provider="openai",
        model="gpt-test",
        content="Done.",
        usage=ProviderUsage(input_tokens=5, output_tokens=7),
        latency_ms=120,
    )
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 6, 26, 12, 0, 1, tzinfo=UTC)

    record = ProviderExecutionRecord(
        id="provider-execution-1",
        request=request,
        result=result,
        status=ProviderExecutionStatus.COMPLETED,
        created_at=created_at,
        completed_at=completed_at,
        runtime_session_id=request.runtime_session_id,
        task_id=request.task_id,
        correlation_id=request.correlation_id,
    )

    assert record.id == "provider-execution-1"
    assert record.request == request
    assert record.result == result
    assert record.result.usage.total_tokens == 12
    assert record.status == ProviderExecutionStatus.COMPLETED


def test_provider_execution_result_has_stable_shape() -> None:
    result = ProviderExecutionResult(
        status=ProviderExecutionStatus.COMPLETED,
        provider="openrouter",
        model="gpt-test",
        content="Done.",
        metadata={"adapter": "openai-compatible"},
    )

    assert result.provider == "openrouter"
    assert result.model == "gpt-test"
    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == "Done."


def test_provider_execution_result_accepts_routing_metadata() -> None:
    result = ProviderExecutionResult(
        status=ProviderExecutionStatus.COMPLETED,
        provider="openrouter",
        model="gpt-test",
        effective_provider_id="mock",
        effective_model="mock-large",
        routing_reason="explicit_request",
        routing_source="explicit_request",
        budget_mode="standard",
        task_type="analysis",
        content="Done.",
    )

    assert result.effective_provider_id == "mock"
    assert result.effective_model == "mock-large"
    assert result.routing_reason == "explicit_request"
    assert result.routing_source == "explicit_request"
    assert result.budget_mode == "standard"
    assert result.task_type == "analysis"


def test_provider_budget_policy_classifications() -> None:
    service = ProviderBudgetPolicyService()

    assert (
        service.resolve(provider_id="mock", model="tiny-mini").classification
        == "cheap"
    )
    assert (
        service.resolve(
            provider_id="mock", model="claude-sonnet-4.5"
        ).classification
        == "balanced"
    )
    assert (
        service.resolve(provider_id="mock", model="gpt-4-opus").classification
        == "premium"
    )


def test_provider_budget_policy_unknown_fallback() -> None:
    service = ProviderBudgetPolicyService()

    result = service.resolve(provider_id="mock", model="model-123")

    assert result.classification == "unknown"
    assert result.warnings == []


def test_provider_budget_policy_warns_on_premium_under_cheap_budget() -> None:
    service = ProviderBudgetPolicyService()

    result = service.resolve(
        provider_id="mock",
        model="gpt-4-opus",
        budget_mode="cheap",
    )

    assert result.classification == "cheap"
    assert result.warnings
    assert "cheap budget_mode" in result.warnings[0]
