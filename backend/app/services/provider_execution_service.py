import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.models.provider_execution import (
    ProviderExecutionRecord,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderExecutionStreamEvent,
)
from app.models.provider_execution_validation import (
    ProviderExecutionValidationIssue,
)
from app.models.provider_routing import (
    ProviderRoutingDecision,
    ProviderRoutingResult,
)
from app.models.runtime_event import EventType, Severity
from app.providers.provider_registry import (
    ProviderRegistry,
    provider_registry,
)
from app.services.event_service import EventService
from app.services.provider_adapter_registry_service import (
    ProviderAdapterRegistryService,
    provider_adapter_registry_service,
)
from app.services.provider_execution_validator_service import (
    ProviderExecutionValidatorService,
    provider_execution_validator_service,
)
from app.services.provider_router_service import (
    ProviderRouterService,
    provider_router_service,
)


class ProviderExecutionService:
    def __init__(
        self,
        adapter_registry: ProviderAdapterRegistryService | None = None,
        router: ProviderRouterService | None = None,
        provider_registry: ProviderRegistry | None = None,
        validator: ProviderExecutionValidatorService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._adapter_registry = (
            adapter_registry or provider_adapter_registry_service
        )
        self._router = router or provider_router_service
        self._provider_registry = provider_registry or provider_registry_default()
        self._validator = validator or provider_execution_validator_service
        self._events = events

    async def complete(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        adapter = self._adapter_registry.get_adapter(request.provider_id)
        return await adapter.complete(request)

    async def stream(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        adapter = self._adapter_registry.get_adapter(request.provider_id)
        async for event in adapter.stream(request):
            yield event

    async def cancel(
        self,
        provider_id: str,
        execution_id: str,
    ) -> None:
        adapter = self._adapter_registry.get_adapter(provider_id)
        await adapter.cancel(execution_id)

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
        self._emit(
            EventType.PROVIDER_EXECUTION_REQUESTED,
            "Provider execution requested",
            request,
            record,
            status=ProviderExecutionStatus.REQUESTED,
        )

        validation = self._validator.validate_request(request)
        if not validation.valid:
            error_message = _validation_error_message(validation.issues)
            issue_codes = [issue.code for issue in validation.issues]
            self._emit(
                EventType.PROVIDER_EXECUTION_VALIDATION_FAILED,
                "Provider execution validation failed",
                request,
                record,
                severity=Severity.ERROR,
                status=ProviderExecutionStatus.FAILED,
                validation_issue_codes=issue_codes,
                error_type="ProviderExecutionValidationError",
                error_message=error_message,
            )
            failed_record = record.model_copy(
                update={
                    "status": ProviderExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "result": _failed_result(
                        request,
                        error_message,
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
            self._emit(
                EventType.PROVIDER_EXECUTION_FAILED,
                "Provider execution failed",
                request,
                failed_record,
                severity=Severity.ERROR,
                status=ProviderExecutionStatus.FAILED,
                validation_issue_codes=issue_codes,
                error_type="ProviderExecutionValidationError",
                error_message=error_message,
            )
            return failed_record

        routing_result = self._router.resolve(
            request.provider,
            request.model,
        )
        if not routing_result.resolved or routing_result.decision is None:
            error_message = (
                routing_result.error_message
                or "Provider routing failed."
            )
            routing_payload = routing_result.model_dump(mode="json")
            failed_metadata = dict(record.metadata)
            failed_metadata["validation"] = validation.metadata
            failed_metadata["routing_result"] = routing_payload
            failed_record = record.model_copy(
                update={
                    "status": ProviderExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "metadata": failed_metadata,
                    "result": _failed_result(
                        request,
                        error_message,
                        {"routing_result": routing_payload},
                    ),
                },
                deep=True,
            )
            self._emit(
                EventType.PROVIDER_EXECUTION_FAILED,
                "Provider execution failed",
                request,
                failed_record,
                severity=Severity.ERROR,
                status=ProviderExecutionStatus.FAILED,
                routing_result=routing_result,
                error_type="ProviderRoutingError",
                error_message=error_message,
            )
            return failed_record

        routing = _routing_metadata(request, routing_result.decision)
        try:
            adapter = self._provider_registry.provider(
                routing_result.decision.adapter_provider_name
            )
            self._emit(
                EventType.PROVIDER_EXECUTION_STARTED,
                "Provider execution started",
                request,
                record,
                status=ProviderExecutionStatus.REQUESTED,
                routing_decision=routing_result.decision,
            )
            result = adapter.execute(request)
        except Exception as exc:
            failed_metadata = dict(record.metadata)
            failed_metadata["validation"] = validation.metadata
            failed_metadata["routing"] = routing
            failed_record = record.model_copy(
                update={
                    "status": ProviderExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "metadata": failed_metadata,
                    "result": _failed_result(
                        request,
                        str(exc),
                        {
                            "error_type": type(exc).__name__,
                            "routing": routing,
                        },
                    ),
                },
                deep=True,
            )
            self._emit(
                EventType.PROVIDER_EXECUTION_FAILED,
                "Provider execution failed",
                request,
                failed_record,
                severity=Severity.ERROR,
                status=ProviderExecutionStatus.FAILED,
                routing_decision=routing_result.decision,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return failed_record

        metadata = dict(record.metadata)
        metadata["validation"] = validation.metadata
        metadata["routing"] = routing
        completed_record = record.model_copy(
            update={
                "status": result.status,
                "completed_at": datetime.now(UTC),
                "result": result,
                "metadata": metadata,
            },
            deep=True,
        )
        if result.status == ProviderExecutionStatus.COMPLETED:
            self._emit(
                EventType.PROVIDER_EXECUTION_COMPLETED,
                "Provider execution completed",
                request,
                completed_record,
                status=result.status,
                routing_decision=routing_result.decision,
                latency_ms=result.latency_ms,
                usage=_usage_metadata(result),
            )
        elif result.status == ProviderExecutionStatus.FAILED:
            self._emit(
                EventType.PROVIDER_EXECUTION_FAILED,
                "Provider execution failed",
                request,
                completed_record,
                severity=Severity.ERROR,
                status=result.status,
                routing_decision=routing_result.decision,
                latency_ms=result.latency_ms,
                usage=_usage_metadata(result),
                error_type="ProviderExecutionError",
                error_message=result.error_message,
            )
        return completed_record

    def _emit(
        self,
        event_type: EventType,
        message: str,
        request: ProviderExecutionRequest,
        record: ProviderExecutionRecord,
        *,
        severity: Severity = Severity.INFO,
        status: ProviderExecutionStatus,
        latency_ms: int | None = None,
        usage: dict | None = None,
        validation_issue_codes: list[str] | None = None,
        routing_decision: ProviderRoutingDecision | None = None,
        routing_result: ProviderRoutingResult | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if self._events is None:
            return
        metadata = {
            "provider": request.provider,
            "requested_provider": request.provider,
            "resolved_provider": (
                routing_decision.provider
                if routing_decision is not None
                else None
            ),
            "adapter_provider": (
                routing_decision.adapter_provider_name
                if routing_decision is not None
                else _routing_adapter_name(routing_result)
            ),
            "model": request.model,
            "mode": request.mode.value,
            "stream_mode": request.stream_mode.value,
            "message_count": len(request.messages),
            "runtime_session_id": request.runtime_session_id,
            "task_id": request.task_id,
            "correlation_id": request.correlation_id,
            "provider_execution_record_id": record.id,
            "status": status.value,
            "latency_ms": latency_ms,
            "usage": usage,
            "validation_issue_codes": validation_issue_codes,
            "error_type": error_type,
            "error_message": error_message,
        }
        self._events.emit_event_sync(
            event_type=event_type,
            message=message,
            severity=severity,
            metadata={
                key: value
                for key, value in metadata.items()
                if value is not None
            },
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


def _routing_metadata(
    request: ProviderExecutionRequest,
    decision: ProviderRoutingDecision,
) -> dict[str, str]:
    return {
        "requested_provider": request.provider,
        "resolved_provider": decision.provider,
        "adapter_provider": decision.adapter_provider_name,
        "resolved_model": decision.model,
    }


def _routing_adapter_name(
    result: ProviderRoutingResult | None,
) -> str | None:
    if result is None:
        return None
    value = result.metadata.get("adapter_provider_name")
    return value if isinstance(value, str) else None


def _usage_metadata(
    result: ProviderExecutionResult,
) -> dict | None:
    if result.usage is None:
        return None
    return {
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
        "estimated_cost": result.usage.estimated_cost,
        "currency": result.usage.currency,
    }


provider_execution_service = ProviderExecutionService()
