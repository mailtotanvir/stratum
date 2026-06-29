import hashlib
import json
from datetime import UTC, datetime

from app.models.agent_execution import (
    AgentExecutionMode,
    AgentExecutionRecord,
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentExecutionStatus,
)
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
)
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service,
)


AGENT_PROVIDER_MODE_MAP = {
    AgentExecutionMode.SINGLE_TURN: ProviderExecutionMode.CHAT,
    AgentExecutionMode.TOOL_ENABLED: ProviderExecutionMode.TOOL_CALL,
}

PROVIDER_AGENT_STATUS_MAP = {
    ProviderExecutionStatus.REQUESTED: AgentExecutionStatus.RUNNING,
    ProviderExecutionStatus.COMPLETED: AgentExecutionStatus.COMPLETED,
    ProviderExecutionStatus.FAILED: AgentExecutionStatus.FAILED,
    ProviderExecutionStatus.CANCELLED: AgentExecutionStatus.CANCELLED,
}


class AgentExecutionService:
    def __init__(
        self,
        provider_execution: ProviderExecutionService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._provider_execution = (
            provider_execution or provider_execution_service
        )
        self._events = events or event_service

    def execute(
        self,
        request: AgentExecutionRequest,
    ) -> AgentExecutionRecord:
        created_at = datetime.now(UTC)
        record = AgentExecutionRecord(
            id=_record_id(request),
            request=request,
            status=AgentExecutionStatus.RUNNING,
            created_at=created_at,
            metadata=dict(request.metadata),
        )
        self._emit(
            EventType.AGENT_EXECUTION_REQUESTED,
            "Agent execution requested",
            record,
            status=AgentExecutionStatus.PENDING,
        )
        self._emit(
            EventType.AGENT_EXECUTION_STARTED,
            "Agent execution started",
            record,
            status=AgentExecutionStatus.RUNNING,
        )

        provider_record = self._provider_execution.execute(
            _provider_request(request)
        )
        status = PROVIDER_AGENT_STATUS_MAP[provider_record.status]
        completed = record.model_copy(
            update={
                "status": status,
                "completed_at": datetime.now(UTC),
                "result": AgentExecutionResult(
                    status=status,
                    provider_execution_record_id=provider_record.id,
                    provider_result=provider_record.result,
                    metadata=dict(request.metadata),
                ),
            },
            deep=True,
        )

        if status == AgentExecutionStatus.COMPLETED:
            self._emit(
                EventType.AGENT_EXECUTION_COMPLETED,
                "Agent execution completed",
                completed,
                status=status,
                provider_execution_id=provider_record.id,
            )
        else:
            self._emit(
                EventType.AGENT_EXECUTION_FAILED,
                "Agent execution failed",
                completed,
                status=status,
                provider_execution_id=provider_record.id,
                severity=Severity.ERROR,
            )
        return completed

    def _emit(
        self,
        event_type: EventType,
        message: str,
        record: AgentExecutionRecord,
        *,
        status: AgentExecutionStatus,
        provider_execution_id: str | None = None,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata = {
            "agent_execution_id": record.id,
            "provider_execution_id": provider_execution_id,
            "provider": record.request.provider,
            "model": record.request.model,
            "runtime_session_id": record.request.runtime_session_id,
            "task_id": record.request.task_id,
            "correlation_id": record.request.correlation_id,
            "status": status.value,
            "message_count": len(record.request.messages),
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


def _provider_request(
    request: AgentExecutionRequest,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=request.provider,
        model=request.model,
        mode=AGENT_PROVIDER_MODE_MAP[request.mode],
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream_mode=request.stream_mode,
        runtime_session_id=request.runtime_session_id,
        task_id=request.task_id,
        correlation_id=request.correlation_id,
        metadata=dict(request.metadata),
    )


def _record_id(request: AgentExecutionRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"agent-execution-{digest}"


agent_execution_service = AgentExecutionService()
