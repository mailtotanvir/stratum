import hashlib
import json
from datetime import UTC, datetime

from app.models.provider_execution import (
    ProviderExecutionRecord,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.models.provider_execution_validation import (
    ProviderExecutionValidationIssue,
)
from app.providers.provider_registry import (
    ProviderRegistry,
    provider_registry,
)
from app.services.provider_execution_validator_service import (
    ProviderExecutionValidatorService,
    provider_execution_validator_service,
)


class ProviderExecutionService:
    def __init__(
        self,
        provider_registry: ProviderRegistry | None = None,
        validator: ProviderExecutionValidatorService | None = None,
    ) -> None:
        self._provider_registry = provider_registry or provider_registry_default()
        self._validator = validator or provider_execution_validator_service

    def execute(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionRecord:
        created_at = datetime.now(UTC)
        record = ProviderExecutionRecord(
            id=_record_id(request),
            request=request,
            status=ProviderExecutionStatus.REQUESTED,
            created_at=created_at,
            runtime_session_id=request.runtime_session_id,
            task_id=request.task_id,
            correlation_id=request.correlation_id,
            metadata=dict(request.metadata),
        )

        validation = self._validator.validate_request(request)
        if not validation.valid:
            return record.model_copy(
                update={
                    "status": ProviderExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "result": _failed_result(
                        request,
                        _validation_error_message(validation.issues),
                        {
                            "validation_issues": [
                                issue.model_dump(mode="json")
                                for issue in validation.issues
                            ]
                        },
                    ),
                },
                deep=True,
            )

        try:
            adapter = self._provider_registry.provider(request.provider)
            result = adapter.execute(request)
        except Exception as exc:
            return record.model_copy(
                update={
                    "status": ProviderExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "result": _failed_result(
                        request,
                        str(exc),
                        {"error_type": type(exc).__name__},
                    ),
                },
                deep=True,
            )

        metadata = dict(record.metadata)
        metadata["validation"] = validation.metadata
        return record.model_copy(
            update={
                "status": result.status,
                "completed_at": datetime.now(UTC),
                "result": result,
                "metadata": metadata,
            },
            deep=True,
        )


def provider_registry_default() -> ProviderRegistry:
    return provider_registry


def _record_id(request: ProviderExecutionRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"provider-execution-{digest}"


def _failed_result(
    request: ProviderExecutionRequest,
    error_message: str,
    metadata: dict,
) -> ProviderExecutionResult:
    return ProviderExecutionResult(
        status=ProviderExecutionStatus.FAILED,
        provider=request.provider,
        model=request.model,
        error_message=error_message,
        metadata=metadata,
    )


def _validation_error_message(
    issues: list[ProviderExecutionValidationIssue],
) -> str:
    return "; ".join(
        f"{issue.code}: {issue.message}" for issue in issues
    )


provider_execution_service = ProviderExecutionService()
