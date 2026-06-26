from app.models.provider_capability import (
    ProviderCapabilityStatus,
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
)
from app.services.provider_execution_validator_service import (
    ProviderExecutionValidatorService,
)


def message() -> ProviderMessage:
    return ProviderMessage(
        role=ProviderMessageRole.USER,
        content="Run preflight validation.",
    )


def request(
    *,
    provider: str = "openai",
    model: str = "gpt-5.5",
    mode: ProviderExecutionMode = ProviderExecutionMode.CHAT,
    stream_mode: ProviderStreamMode = ProviderStreamMode.NONE,
    max_tokens: int | None = None,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=provider,
        model=model,
        mode=mode,
        messages=[message()],
        stream_mode=stream_mode,
        max_tokens=max_tokens,
    )


def registry_with(
    *models: ProviderModelDescriptor,
) -> ProviderCapabilityRegistryService:
    return ProviderCapabilityRegistryService(models=models)


def test_valid_chat_request_for_supported_model() -> None:
    result = ProviderExecutionValidatorService().validate_request(request())

    assert result.valid is True
    assert result.issues == []


def test_unknown_model_invalid() -> None:
    result = ProviderExecutionValidatorService().validate_request(
        request(provider="missing", model="model")
    )

    assert result.valid is False
    assert [issue.code for issue in result.issues] == ["unknown_model"]


def test_unsupported_execution_mode_invalid() -> None:
    service = ProviderExecutionValidatorService(
        registry_with(
            ProviderModelDescriptor(
                provider="test",
                model="chat-only",
                capabilities=[ProviderModelCapability.CHAT],
            )
        )
    )

    result = service.validate_request(
        request(
            provider="test",
            model="chat-only",
            mode=ProviderExecutionMode.COMPLETION,
        )
    )

    assert result.valid is False
    assert [issue.code for issue in result.issues] == [
        "unsupported_execution_mode"
    ]


def test_streaming_without_streaming_capability_invalid() -> None:
    service = ProviderExecutionValidatorService(
        registry_with(
            ProviderModelDescriptor(
                provider="test",
                model="chat-only",
                capabilities=[ProviderModelCapability.CHAT],
            )
        )
    )

    result = service.validate_request(
        request(
            provider="test",
            model="chat-only",
            stream_mode=ProviderStreamMode.SSE,
        )
    )

    assert result.valid is False
    assert [issue.code for issue in result.issues] == [
        "unsupported_streaming"
    ]


def test_streaming_with_streaming_capability_valid() -> None:
    result = ProviderExecutionValidatorService().validate_request(
        request(stream_mode=ProviderStreamMode.SSE)
    )

    assert result.valid is True


def test_max_tokens_above_descriptor_limit_invalid() -> None:
    service = ProviderExecutionValidatorService(
        registry_with(
            ProviderModelDescriptor(
                provider="test",
                model="limited",
                capabilities=[ProviderModelCapability.CHAT],
                max_output_tokens=10,
            )
        )
    )

    result = service.validate_request(
        request(provider="test", model="limited", max_tokens=11)
    )

    assert result.valid is False
    assert [issue.code for issue in result.issues] == [
        "max_tokens_exceeds_model_limit"
    ]


def test_disabled_or_unavailable_model_invalid() -> None:
    for status in (
        ProviderCapabilityStatus.DISABLED,
        ProviderCapabilityStatus.UNAVAILABLE,
    ):
        service = ProviderExecutionValidatorService(
            registry_with(
                ProviderModelDescriptor(
                    provider="test",
                    model=status.value,
                    status=status,
                    capabilities=[ProviderModelCapability.CHAT],
                )
            )
        )

        result = service.validate_request(
            request(provider="test", model=status.value)
        )

        assert result.valid is False
        assert [issue.code for issue in result.issues] == [
            "model_unavailable"
        ]


def test_validation_metadata_includes_descriptor_details() -> None:
    result = ProviderExecutionValidatorService().validate_request(request())

    assert result.metadata == {
        "provider": "openai",
        "model": "gpt-5.5",
        "capabilities": [
            "chat",
            "tool_call",
            "streaming",
            "json_output",
        ],
        "status": "available",
    }


def test_multiple_issues_can_be_returned() -> None:
    service = ProviderExecutionValidatorService(
        registry_with(
            ProviderModelDescriptor(
                provider="test",
                model="limited-disabled",
                status=ProviderCapabilityStatus.DISABLED,
                capabilities=[ProviderModelCapability.CHAT],
                max_output_tokens=10,
            )
        )
    )

    result = service.validate_request(
        request(
            provider="test",
            model="limited-disabled",
            mode=ProviderExecutionMode.TOOL_CALL,
            stream_mode=ProviderStreamMode.SSE,
            max_tokens=11,
        )
    )

    assert result.valid is False
    assert [issue.code for issue in result.issues] == [
        "model_unavailable",
        "unsupported_execution_mode",
        "unsupported_streaming",
        "max_tokens_exceeds_model_limit",
    ]
