from app.models.provider_capability import (
    ProviderCapabilityStatus,
    ProviderModelCapability,
    ProviderModelDescriptor,
)
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderStreamMode,
)
from app.models.provider_execution_validation import (
    ProviderExecutionValidationIssue,
    ProviderExecutionValidationResult,
)
from app.services.provider_capability_registry_service import (
    ProviderCapabilityRegistryService,
    provider_capability_registry_service,
)


EXECUTION_MODE_CAPABILITY_MAP = {
    ProviderExecutionMode.CHAT: ProviderModelCapability.CHAT,
    ProviderExecutionMode.COMPLETION: ProviderModelCapability.COMPLETION,
    ProviderExecutionMode.TOOL_CALL: ProviderModelCapability.TOOL_CALL,
}


class ProviderExecutionValidatorService:
    def __init__(
        self,
        registry: ProviderCapabilityRegistryService | None = None,
    ) -> None:
        self._registry = registry or provider_capability_registry_service

    def validate_request(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionValidationResult:
        issues: list[ProviderExecutionValidationIssue] = []
        descriptor = self._descriptor(request, issues)
        metadata = (
            _descriptor_metadata(descriptor)
            if descriptor is not None
            else {
                "provider": request.provider,
                "model": request.model,
            }
        )

        if descriptor is not None:
            self._validate_availability(descriptor, issues)
            self._validate_mode(request, descriptor, issues)
            self._validate_streaming(request, descriptor, issues)
            self._validate_max_tokens(request, descriptor, issues)

        return ProviderExecutionValidationResult(
            valid=not issues,
            issues=issues,
            metadata=metadata,
        )

    def _descriptor(
        self,
        request: ProviderExecutionRequest,
        issues: list[ProviderExecutionValidationIssue],
    ) -> ProviderModelDescriptor | None:
        try:
            return self._registry.get_model(request.provider, request.model)
        except ValueError:
            issues.append(
                ProviderExecutionValidationIssue(
                    code="unknown_model",
                    message=(
                        "Provider model is not registered: "
                        f"{request.provider}/{request.model}"
                    ),
                    metadata={
                        "provider": request.provider,
                        "model": request.model,
                    },
                )
            )
            return None

    @staticmethod
    def _validate_availability(
        descriptor: ProviderModelDescriptor,
        issues: list[ProviderExecutionValidationIssue],
    ) -> None:
        if descriptor.status != ProviderCapabilityStatus.AVAILABLE:
            issues.append(
                ProviderExecutionValidationIssue(
                    code="model_unavailable",
                    message=(
                        "Provider model is not available: "
                        f"{descriptor.provider}/{descriptor.model}"
                    ),
                    metadata={
                        "provider": descriptor.provider,
                        "model": descriptor.model,
                        "status": descriptor.status.value,
                    },
                )
            )

    @staticmethod
    def _validate_mode(
        request: ProviderExecutionRequest,
        descriptor: ProviderModelDescriptor,
        issues: list[ProviderExecutionValidationIssue],
    ) -> None:
        capability = EXECUTION_MODE_CAPABILITY_MAP[request.mode]
        if capability not in descriptor.capabilities:
            issues.append(
                ProviderExecutionValidationIssue(
                    code="unsupported_execution_mode",
                    message=(
                        "Provider model does not support execution mode: "
                        f"{request.mode.value}"
                    ),
                    metadata={
                        "provider": descriptor.provider,
                        "model": descriptor.model,
                        "mode": request.mode.value,
                        "required_capability": capability.value,
                    },
                )
            )

    @staticmethod
    def _validate_streaming(
        request: ProviderExecutionRequest,
        descriptor: ProviderModelDescriptor,
        issues: list[ProviderExecutionValidationIssue],
    ) -> None:
        if (
            request.stream_mode != ProviderStreamMode.NONE
            and ProviderModelCapability.STREAMING
            not in descriptor.capabilities
        ):
            issues.append(
                ProviderExecutionValidationIssue(
                    code="unsupported_streaming",
                    message="Provider model does not support streaming.",
                    metadata={
                        "provider": descriptor.provider,
                        "model": descriptor.model,
                        "stream_mode": request.stream_mode.value,
                    },
                )
            )

    @staticmethod
    def _validate_max_tokens(
        request: ProviderExecutionRequest,
        descriptor: ProviderModelDescriptor,
        issues: list[ProviderExecutionValidationIssue],
    ) -> None:
        if (
            request.max_tokens is not None
            and descriptor.max_output_tokens is not None
            and request.max_tokens > descriptor.max_output_tokens
        ):
            issues.append(
                ProviderExecutionValidationIssue(
                    code="max_tokens_exceeds_model_limit",
                    message=(
                        "Requested max_tokens exceeds model output limit."
                    ),
                    metadata={
                        "provider": descriptor.provider,
                        "model": descriptor.model,
                        "requested_max_tokens": request.max_tokens,
                        "model_max_output_tokens": (
                            descriptor.max_output_tokens
                        ),
                    },
                )
            )


def _descriptor_metadata(
    descriptor: ProviderModelDescriptor,
) -> dict[str, object]:
    return {
        "provider": descriptor.provider,
        "model": descriptor.model,
        "capabilities": [
            capability.value for capability in descriptor.capabilities
        ],
        "status": descriptor.status.value,
    }


provider_execution_validator_service = ProviderExecutionValidatorService()
