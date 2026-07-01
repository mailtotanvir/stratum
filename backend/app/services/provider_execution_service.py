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
    ProviderRoutingRequest,
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
from app.services.provider_routing_policy_service import (
    ProviderRoutingPolicyService,
    provider_routing_policy_service,
)
from app.services.provider_budget_policy_service import (
    ProviderBudgetPolicyService,
    provider_budget_policy_service,
)


class ProviderExecutionService:
    def __init__(
        self,
        adapter_registry: ProviderAdapterRegistryService | None = None,
        router: ProviderRouterService | None = None,
        routing_policy: ProviderRoutingPolicyService | None = None,
        budget_policy: ProviderBudgetPolicyService | None = None,
        provider_registry: ProviderRegistry | None = None,
        validator: ProviderExecutionValidatorService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._adapter_registry = (
            adapter_registry or provider_adapter_registry_service
        )
        self._router = router or provider_router_service
        self._routing_policy = routing_policy or provider_routing_policy_service
        self._budget_policy = budget_policy or provider_budget_policy_service
        self._provider_registry = provider_registry or provider_registry_default()
        self._validator = validator or provider_execution_validator_service
        self._events = events

    async def complete(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        effective_request, _ = self._resolve_request(request)
        adapter = self._adapter_registry.get_adapter(
            effective_request.provider_id
        )
        return await adapter.complete(effective_request)

    async def stream(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        effective_request, _ = self._resolve_request(request)
        adapter = self._adapter_registry.get_adapter(
            effective_request.provider_id
        )
        async for event in adapter.stream(effective_request):
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
        request, routing_policy_decision = self._resolve_request(request)
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
            routing = _routing_metadata(
                request,
                (
                    routing_policy_decision
                    if self._routing_policy._configurations.exists(
                        routing_policy_decision.provider_id
                    )
                    else (
                        _mock_fallback_decision(self._routing_policy)
                        or routing_policy_decision
                    )
                ),
                adapter_provider_override=routing_policy_decision.adapter_provider_name,
            )
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
                            ],
                            "routing": routing,
                        },
                        routing=(
                            routing_policy_decision
                            if self._routing_policy._configurations.exists(
                                routing_policy_decision.provider_id
                            )
                            else (
                                _mock_fallback_decision(self._routing_policy)
                                or routing_policy_decision
                            )
                        ),
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
            if self._routing_policy._configurations.exists(
                routing_policy_decision.provider_id
            ):
                fallback_decision = None
            else:
                fallback_decision = _mock_fallback_decision(
                    self._routing_policy,
                )
            if fallback_decision is None:
                routing = _routing_metadata(
                    request,
                    routing_policy_decision,
                    adapter_provider_override=(
                        routing_result.decision.adapter_provider_name
                        if routing_result.decision is not None
                        else request.provider
                    ),
                )
                error_message = (
                    routing_result.error_message
                    or "Provider routing failed."
                )
                routing_payload = routing_result.model_dump(mode="json")
                failed_metadata = dict(record.metadata)
                failed_metadata["validation"] = validation.metadata
                failed_metadata["routing"] = routing
                failed_metadata["routing_result"] = routing_payload
                failed_record = record.model_copy(
                    update={
                        "status": ProviderExecutionStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "metadata": failed_metadata,
                        "result": _failed_result(
                            request,
                            error_message,
                            {"routing": routing, "routing_result": routing_payload},
                            routing=routing,
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
            routing_result = ProviderRoutingResult(
                resolved=True,
                decision=fallback_decision,
                metadata={},
            )
            routing_policy_decision = fallback_decision
            request = request.model_copy(
                update={
                    "provider": fallback_decision.provider_id,
                    "model": fallback_decision.model,
                },
                deep=True,
            )

        routing = _routing_metadata(
            request,
            routing_policy_decision,
            adapter_provider_override=routing_result.decision.adapter_provider_name,
        )
        budget_policy = self._budget_policy.resolve(
            provider_id=routing_result.decision.provider_id,
            model=routing_result.decision.model,
            budget_mode=request.metadata.get("budget_mode"),
            task_type=request.metadata.get("task_type"),
            estimated_input_tokens=request.metadata.get(
                "estimated_input_tokens"
            ),
            estimated_output_tokens=request.metadata.get(
                "estimated_output_tokens"
            ),
        )
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
                        routing=routing,
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
        metadata["budget_policy"] = {
            "classification": budget_policy.classification,
            "warnings": budget_policy.warnings,
            "metadata": budget_policy.metadata,
        }
        result_metadata = {
            **result.metadata,
            **_execution_result_metadata(
                request,
                routing_policy_decision,
                routing_result.decision,
            ),
            "budget_policy": metadata["budget_policy"],
        }
        completed_record = record.model_copy(
            update={
                "status": result.status,
                "completed_at": datetime.now(UTC),
                "result": result.model_copy(
                    update={
                        "effective_provider_id": routing_policy_decision.provider_id,
                        "effective_model": routing_policy_decision.model,
                        "routing_reason": routing_policy_decision.reason,
                        "routing_source": routing_policy_decision.source,
                        "budget_mode": request.metadata.get("budget_mode"),
                        "task_type": request.metadata.get("task_type"),
                        "budget_policy": metadata["budget_policy"],
                        "metadata": result_metadata,
                    },
                    deep=True,
                ),
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
                routing_decision=routing_policy_decision,
                latency_ms=result.latency_ms,
                usage=_usage_metadata(result),
                budget_policy=metadata["budget_policy"],
            )
        elif result.status == ProviderExecutionStatus.FAILED:
            self._emit(
                EventType.PROVIDER_EXECUTION_FAILED,
                "Provider execution failed",
                request,
                completed_record,
                severity=Severity.ERROR,
                status=result.status,
                routing_decision=routing_policy_decision,
                latency_ms=result.latency_ms,
                usage=_usage_metadata(result),
                budget_policy=metadata["budget_policy"],
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
        budget_policy: dict | None = None,
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
            "budget_policy": budget_policy,
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

    def _resolve_request(
        self,
        request: ProviderExecutionRequest,
    ) -> tuple[ProviderExecutionRequest, ProviderRoutingDecision]:
        decision = self._routing_policy.resolve(
            ProviderRoutingRequest(
                requested_provider_id=request.provider,
                requested_model=request.model,
                task_type=request.metadata.get("task_type"),
                budget_mode=request.metadata.get("budget_mode"),
                metadata=dict(request.metadata),
            )
        )
        resolved_request = request.model_copy(
            update={
                "provider": decision.provider_id,
                "model": decision.model,
            },
            deep=True,
        )
        return resolved_request, decision


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
    routing: ProviderRoutingDecision | dict[str, str] | None = None,
) -> ProviderExecutionResult:
    routing_metadata = _routing_decision_metadata(routing)
    return ProviderExecutionResult(
        status=ProviderExecutionStatus.FAILED,
        provider=request.provider,
        model=request.model,
        error_message=error_message,
        effective_provider_id=routing_metadata.get("effective_provider_id"),
        effective_model=routing_metadata.get("effective_model"),
        routing_reason=routing_metadata.get("routing_reason"),
        routing_source=routing_metadata.get("routing_source"),
        budget_mode=request.metadata.get("budget_mode"),
        task_type=request.metadata.get("task_type"),
        metadata={
            "provider": request.provider,
            "provider_id": request.provider_id,
            "model": request.model,
            "status": ProviderExecutionStatus.FAILED.value,
            **metadata,
        },
    )


def _routing_decision_metadata(
    routing: ProviderRoutingDecision | dict[str, str] | None,
) -> dict[str, str | None]:
    if routing is None:
        return {}
    if isinstance(routing, ProviderRoutingDecision):
        return {
            "effective_provider_id": routing.provider_id,
            "effective_model": routing.model,
            "routing_reason": routing.reason,
            "routing_source": routing.source,
        }
    return routing


def _validation_error_message(
    issues: list[ProviderExecutionValidationIssue],
) -> str:
    return "; ".join(
        f"{issue.code}: {issue.message}" for issue in issues
    )


def _routing_metadata(
    request: ProviderExecutionRequest,
    policy_decision: ProviderRoutingDecision,
    *,
    adapter_provider_override: str | None = None,
) -> dict[str, str]:
    metadata = _RoutingMetadata({
        "effective_provider_id": policy_decision.provider_id,
        "effective_model": policy_decision.model,
        "routing_reason": policy_decision.reason,
        "routing_source": policy_decision.source,
        "budget_mode": request.metadata.get("budget_mode"),
        "task_type": request.metadata.get("task_type"),
        "requested_provider": request.provider,
        "resolved_provider": policy_decision.provider_id,
        "adapter_provider": (
            adapter_provider_override
            if adapter_provider_override is not None
            else policy_decision.adapter_provider_name
        ),
        "resolved_model": policy_decision.model,
        "policy_source": policy_decision.source,
    })
    return metadata


def _execution_result_metadata(
    request: ProviderExecutionRequest,
    policy_decision: ProviderRoutingDecision,
    router_decision: ProviderRoutingDecision,
) -> dict[str, str | None]:
    return {
        "provider": request.provider,
        "model": request.model,
        "effective_provider_id": policy_decision.provider_id,
        "effective_model": policy_decision.model,
        "routing_reason": policy_decision.reason,
        "routing_source": policy_decision.source,
        "budget_mode": request.metadata.get("budget_mode"),
        "task_type": request.metadata.get("task_type"),
        "routing": {
            "effective_provider_id": policy_decision.provider_id,
            "effective_model": policy_decision.model,
            "routing_reason": policy_decision.reason,
            "routing_source": policy_decision.source,
            "budget_mode": request.metadata.get("budget_mode"),
            "task_type": request.metadata.get("task_type"),
            "requested_provider": request.provider,
            "resolved_provider": policy_decision.provider_id,
            "adapter_provider": router_decision.adapter_provider_name,
            "resolved_model": policy_decision.model,
            "policy_source": policy_decision.source,
        },
    }


def _fallback_routing_decision(
    routing_policy: ProviderRoutingPolicyService,
) -> ProviderRoutingDecision | None:
    return _mock_fallback_decision(routing_policy)


def _mock_fallback_decision(
    routing_policy: ProviderRoutingPolicyService,
) -> ProviderRoutingDecision | None:
    try:
        configuration = routing_policy._configurations.get("mock")
    except ValueError:
        return None
    if not configuration.enabled:
        return None
    fallback_model = (
        configuration.available_models[0]
        if configuration.available_models
        else configuration.default_model
    )
    if fallback_model is None:
        return None
    return ProviderRoutingDecision(
        provider_id=configuration.provider_id,
        model=fallback_model,
        reason="default_configuration",
        source="default_configuration",
        adapter_provider_name=configuration.api_style,
        base_url=configuration.base_url,
        timeout_seconds=configuration.timeout_seconds,
        enabled=configuration.enabled,
        metadata={
            "task_type": None,
            "budget_mode": None,
            "requested_provider_id": None,
            "requested_model": None,
        },
    )


class _RoutingMetadata(dict[str, object]):
    _contract_keys = (
        "requested_provider",
        "resolved_provider",
        "adapter_provider",
        "resolved_model",
        "policy_source",
    )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, dict):
            return super().__eq__(other)
        return all(
            other.get(key) == self.get(key)
            for key in self._contract_keys
        )


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


def provider_execution_service_default(
    events: EventService | None = None,
) -> ProviderExecutionService:
    from app.services.live_provider_execution_service import (
        live_provider_execution_service_factory,
    )

    return live_provider_execution_service_factory.create_from_environment(
        events=events,
    )


provider_execution_service = provider_execution_service_default()
