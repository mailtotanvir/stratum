import hashlib
import json

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStreamEvent,
)
from app.models.provider_execution_events import (
    ProviderExecutionCompletedEvent,
    ProviderExecutionCancelledEvent,
    ProviderExecutionFailedEvent,
    ProviderExecutionRequestedEvent,
    ProviderExecutionStreamCompletedEvent,
    ProviderExecutionStreamDeltaEvent,
    ProviderExecutionStreamFailedEvent,
    ProviderExecutionStreamStartedEvent,
)
from app.models.runtime_event import EventType, RuntimeEvent


class ProviderExecutionEventFactory:
    def execution_id(self, request: ProviderExecutionRequest) -> str:
        payload = json.dumps(
            request.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"provider-execution-{digest}"

    def create_requested(
        self,
        request: ProviderExecutionRequest,
        execution_id: str,
    ) -> ProviderExecutionRequestedEvent:
        return ProviderExecutionRequestedEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            metadata=dict(request.metadata),
        )

    def create_completed(
        self,
        request: ProviderExecutionRequest,
        result: ProviderExecutionResult,
        execution_id: str,
    ) -> ProviderExecutionCompletedEvent:
        return ProviderExecutionCompletedEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            usage=result.usage,
            result_metadata=dict(result.metadata),
            metadata=dict(request.metadata),
        )

    def create_failed(
        self,
        request: ProviderExecutionRequest,
        error: Exception,
        execution_id: str,
    ) -> ProviderExecutionFailedEvent:
        return ProviderExecutionFailedEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            error_type=type(error).__name__,
            error_message=str(error) or type(error).__name__,
            metadata=dict(request.metadata),
        )

    def build_cancelled(
        self,
        *,
        event_id: int,
        timestamp: str,
        provider_id: str,
        model: str,
        execution_id: str,
        reason: str,
        correlation_id: str | None = None,
        capability: str | None = None,
        metadata: dict | None = None,
    ) -> RuntimeEvent:
        payload = ProviderExecutionCancelledEvent(
            provider_id=provider_id,
            model=model,
            execution_id=execution_id,
            correlation_id=correlation_id,
            capability=capability,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        return RuntimeEvent(
            id=event_id,
            ts=timestamp,
            type=EventType.PROVIDER_EXECUTION_CANCELLED,
            message="Provider execution cancelled",
            metadata=payload.model_dump(mode="json"),
        )

    def create_stream_started(
        self,
        request: ProviderExecutionRequest,
        execution_id: str,
    ) -> ProviderExecutionStreamStartedEvent:
        return ProviderExecutionStreamStartedEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            sequence=0,
            metadata=dict(request.metadata),
        )

    def create_stream_delta(
        self,
        request: ProviderExecutionRequest,
        event: ProviderExecutionStreamEvent,
        execution_id: str,
    ) -> ProviderExecutionStreamDeltaEvent:
        return ProviderExecutionStreamDeltaEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            sequence=event.sequence,
            content=event.content,
            metadata={
                **request.metadata,
                **event.metadata,
            },
        )

    def create_stream_completed(
        self,
        request: ProviderExecutionRequest,
        execution_id: str,
        sequence: int,
    ) -> ProviderExecutionStreamCompletedEvent:
        return ProviderExecutionStreamCompletedEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            sequence=sequence,
            metadata=dict(request.metadata),
        )

    def create_stream_failed(
        self,
        request: ProviderExecutionRequest,
        error: Exception,
        execution_id: str,
        sequence: int,
    ) -> ProviderExecutionStreamFailedEvent:
        return ProviderExecutionStreamFailedEvent(
            provider_id=request.provider_id,
            model=request.model,
            execution_id=execution_id,
            correlation_id=request.correlation_id,
            capability=request.mode.value,
            sequence=sequence,
            error_type=type(error).__name__,
            error_message=str(error) or type(error).__name__,
            metadata=dict(request.metadata),
        )


provider_execution_event_factory = ProviderExecutionEventFactory()
