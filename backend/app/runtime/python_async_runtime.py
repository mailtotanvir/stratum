from collections.abc import AsyncIterator

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStreamEvent,
)
from app.models.runtime_event import EventType, Severity
from app.providers.base import ProviderAdapterError
from app.services.event_service import EventService, event_service
from app.services.governance_service import GovernanceService
from app.services.interrupt_service import InterruptService, interrupt_service
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service,
)
from app.services.provider_execution_event_factory import (
    ProviderExecutionEventFactory,
    provider_execution_event_factory,
)
from app.services.reflection_service import ReflectionService, reflection_service
from app.services.runtime_execution_service import (
    RuntimeExecutionService,
    runtime_execution_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.stop_service import StopService, stop_service


class PythonAsyncRuntime:
    def __init__(
        self,
        events: EventService | None = None,
        executions: RuntimeExecutionService | None = None,
        governance: GovernanceService | None = None,
        reflections: ReflectionService | None = None,
        interrupts: InterruptService | None = None,
        stops: StopService | None = None,
        sessions: RuntimeSessionService | None = None,
        provider_execution: ProviderExecutionService | None = None,
        provider_events: ProviderExecutionEventFactory | None = None,
    ) -> None:
        self._events = events or event_service
        self._executions = executions or runtime_execution_service
        self._governance = governance or GovernanceService(self._events)
        self._reflections = reflections or reflection_service
        self._interrupts = interrupts or interrupt_service
        self._stops = stops or stop_service
        self._sessions = sessions or runtime_session_service
        self._provider_execution = (
            provider_execution or provider_execution_service
        )
        self._provider_events = (
            provider_events or provider_execution_event_factory
        )

    async def _execute_provider_request(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        execution_id = self._provider_events.execution_id(request)
        requested = self._provider_events.create_requested(
            request,
            execution_id,
        )
        await self._events.emit_event(
            event_type=EventType.PROVIDER_EXECUTION_REQUESTED,
            message="Provider execution requested",
            metadata=requested.model_dump(mode="json"),
        )
        try:
            result = await self._provider_execution.complete(request)
        except (ProviderAdapterError, ValueError) as exc:
            failed = self._provider_events.create_failed(
                request,
                exc,
                execution_id,
            )
            await self._events.emit_event(
                event_type=EventType.PROVIDER_EXECUTION_FAILED,
                message="Provider execution failed",
                severity=Severity.ERROR,
                metadata=failed.model_dump(mode="json"),
            )
            raise

        completed = self._provider_events.create_completed(
            request,
            result,
            execution_id,
        )
        await self._events.emit_event(
            event_type=EventType.PROVIDER_EXECUTION_COMPLETED,
            message="Provider execution completed",
            metadata=completed.model_dump(mode="json"),
        )
        return result

    async def _stream_provider_request(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        execution_id = self._provider_events.execution_id(request)
        started = self._provider_events.create_stream_started(
            request,
            execution_id,
        )
        await self._events.emit_event(
            event_type=EventType.PROVIDER_EXECUTION_STREAM_STARTED,
            message="Provider execution stream started",
            metadata=started.model_dump(mode="json"),
        )

        next_sequence = 1
        try:
            async for event in self._provider_execution.stream(request):
                next_sequence = max(next_sequence, event.sequence + 1)
                if event.event_type == "delta":
                    delta = self._provider_events.create_stream_delta(
                        request,
                        event,
                        execution_id,
                    )
                    await self._events.emit_event(
                        event_type=(
                            EventType.PROVIDER_EXECUTION_STREAM_DELTA
                        ),
                        message="Provider execution stream delta",
                        metadata=delta.model_dump(mode="json"),
                    )
                yield event
        except ProviderAdapterError as exc:
            failed = self._provider_events.create_stream_failed(
                request,
                exc,
                execution_id,
                next_sequence,
            )
            await self._events.emit_event(
                event_type=EventType.PROVIDER_EXECUTION_STREAM_FAILED,
                message="Provider execution stream failed",
                severity=Severity.ERROR,
                metadata=failed.model_dump(mode="json"),
            )
            raise

        completed = self._provider_events.create_stream_completed(
            request,
            execution_id,
            next_sequence,
        )
        await self._events.emit_event(
            event_type=EventType.PROVIDER_EXECUTION_STREAM_COMPLETED,
            message="Provider execution stream completed",
            metadata=completed.model_dump(mode="json"),
        )

    async def run_task(self, task_id: str) -> dict:
        governance = self._governance_preview()
        reflection = self._governance.preview_reflection()
        if reflection["recommended"]:
            request = self._reflections.create_request(
                task_id=task_id,
                reasons=reflection["reasons"],
            )
            await self._events.emit_event(
                event_type=EventType.REFLECTION_REQUESTED,
                message=f"Reflection requested for task: {task_id}",
                metadata={
                    "reflection_request_id": request.id,
                    "task_id": request.task_id,
                    "status": request.status,
                    "reasons": self._reflections.reasons_for(request),
                    "created_at": request.created_at.isoformat(),
                },
            )

        if governance["decision"] == "block":
            await self._events.emit_event(
                event_type=EventType.RUNTIME_GOVERNANCE_BLOCKED,
                message=f"Runtime governance blocked task: {task_id}",
                severity=Severity.WARNING,
                metadata={
                    "task_id": task_id,
                    "decision": governance["decision"],
                    "reasons": governance["reasons"],
                },
            )
            return {
                "task_id": task_id,
                "status": "blocked",
                "governance": governance,
            }

        if governance["decision"] == "warn":
            await self._events.emit_event(
                event_type=EventType.RUNTIME_GOVERNANCE_WARNING,
                message=f"Runtime governance warning for task: {task_id}",
                severity=Severity.WARNING,
                metadata={
                    "task_id": task_id,
                    "decision": governance["decision"],
                    "reasons": governance["reasons"],
                },
            )

        session = self._sessions.create_session(task_id)
        await self._emit_session_event(
            EventType.RUNTIME_SESSION_CREATED,
            session,
            message=f"Runtime session created for task: {task_id}",
        )
        session = self._sessions.mark_running(session.id)
        await self._emit_session_event(
            EventType.RUNTIME_SESSION_RUNNING,
            session,
            message=f"Runtime session running for task: {task_id}",
        )
        self._executions.start(task_id)
        await self._events.emit_event(
            event_type=EventType.RUNTIME_TASK_STARTED,
            message=f"Runtime task started: {task_id}",
            metadata={
                "task_id": task_id,
                "runtime": "python_async",
            },
        )
        return {
            "task_id": task_id,
            "status": "started",
            "governance": governance,
        }

    async def interrupt(self, task_id: str, reason: str) -> dict:
        request = self._interrupts.create_request(task_id=task_id, reason=reason)
        await self._events.emit_event(
            event_type=EventType.INTERRUPT_REQUESTED,
            message=f"Interrupt requested for task: {task_id}",
            metadata=self._interrupt_metadata(request),
        )

        request = self._interrupts.apply_request(request.id)
        await self._events.emit_event(
            event_type=EventType.INTERRUPT_APPLIED,
            message=f"Interrupt applied for task: {task_id}",
            metadata=self._interrupt_metadata(request),
        )

        self._executions.interrupt(task_id)
        session = self._sessions.latest_session_for_task(task_id)
        if session is not None:
            session = self._sessions.mark_interrupted(session.id)
            await self._emit_session_event(
                EventType.RUNTIME_SESSION_INTERRUPTED,
                session,
                message=f"Runtime session interrupted for task: {task_id}",
            )
        await self._events.emit_event(
            event_type=EventType.RUNTIME_TASK_INTERRUPTED,
            message=f"Runtime task interrupted: {task_id}",
            severity=Severity.WARNING,
            metadata={
                "task_id": task_id,
                "runtime": "python_async",
                "reason": reason,
            },
        )
        return {
            "runtime": "python_async",
            "task_id": task_id,
            "status": "interrupted",
            "reason": reason,
            "interrupt_request_id": request.id,
        }

    def _interrupt_metadata(self, request) -> dict[str, object]:
        metadata = {
            "interrupt_request_id": request.id,
            "task_id": request.task_id,
            "reason": request.reason,
            "status": request.status,
            "created_at": request.created_at.isoformat(),
        }
        if request.resolved_at is not None:
            metadata["resolved_at"] = request.resolved_at.isoformat()
        return metadata

    def _governance_preview(self) -> dict:
        preview = self._governance.preview_decision()
        return {
            "decision": preview["decision"],
            "reasons": preview["reasons"],
        }

    async def stop(self, task_id: str, reason: str) -> dict:
        request = self._stops.create_request(task_id=task_id, reason=reason)
        await self._events.emit_event(
            event_type=EventType.STOP_REQUESTED,
            message=f"Stop requested for task: {task_id}",
            metadata=self._stop_metadata(request),
        )

        request = self._stops.apply_request(request.id)
        await self._events.emit_event(
            event_type=EventType.STOP_APPLIED,
            message=f"Stop applied for task: {task_id}",
            metadata=self._stop_metadata(request),
        )

        self._executions.stop(task_id)
        session = self._sessions.latest_session_for_task(task_id)
        if session is not None:
            session = self._sessions.mark_stopped(session.id)
            await self._emit_session_event(
                EventType.RUNTIME_SESSION_STOPPED,
                session,
                message=f"Runtime session stopped for task: {task_id}",
            )
        await self._events.emit_event(
            event_type=EventType.RUNTIME_TASK_STOPPED,
            message=f"Runtime task stopped: {task_id}",
            severity=Severity.WARNING,
            metadata={
                "task_id": task_id,
                "runtime": "python_async",
                "reason": reason,
            },
        )
        return {
            "runtime": "python_async",
            "task_id": task_id,
            "status": "stopped",
            "reason": reason,
            "stop_request_id": request.id,
        }

    def _stop_metadata(self, request) -> dict[str, object]:
        metadata = {
            "stop_request_id": request.id,
            "task_id": request.task_id,
            "reason": request.reason,
            "status": request.status,
            "created_at": request.created_at.isoformat(),
        }
        if request.resolved_at is not None:
            metadata["resolved_at"] = request.resolved_at.isoformat()
        return metadata

    async def _emit_session_event(self, event_type, session, message: str) -> None:
        metadata = {
            "runtime_session_id": session.id,
            "task_id": session.task_id,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
        }
        if session.completed_at is not None:
            metadata["completed_at"] = session.completed_at.isoformat()

        await self._events.emit_event(
            event_type=event_type,
            message=message,
            metadata=metadata,
        )


python_async_runtime = PythonAsyncRuntime()
