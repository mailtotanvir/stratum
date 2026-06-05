from typing import Any

from app.models.runtime_event import EventType
from app.services.event_service import EventService, event_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.tool_execution_service import (
    ToolExecutionService,
    tool_execution_service,
)
from app.services.tool_invocation_service import (
    ToolInvocationService,
    tool_invocation_service,
)
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)


class WorkLoopService:
    def __init__(
        self,
        sessions: RuntimeSessionService | None = None,
        tools: ToolRegistryService | None = None,
        invocations: ToolInvocationService | None = None,
        execution: ToolExecutionService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._sessions = sessions or runtime_session_service
        self._tools = tools or tool_registry_service
        self._invocations = invocations or tool_invocation_service
        self._execution = execution or tool_execution_service
        self._events = events or event_service

    async def run_single_step(
        self,
        session_id: str,
        tool_name: str,
        input_payload: dict | None,
    ) -> dict[str, str]:
        runtime_session = self._sessions.get_session(session_id)
        tool = self._tools.get_tool_by_name(tool_name)

        await self._events.emit_event(
            event_type=EventType.WORK_LOOP_STARTED,
            message=f"Work loop started: {tool_name}",
            metadata={
                "session_id": runtime_session.id,
                "task_id": runtime_session.task_id,
                "tool_id": tool.id,
                "tool_name": tool.name,
            },
        )

        invocation = self._invocations.create_invocation_without_event(
            session_id=session_id,
            tool_id=tool.id,
            input_payload=input_payload,
        )
        await self._emit_invocation_event(
            EventType.TOOL_INVOCATION_REQUESTED,
            invocation,
            message=f"Tool invocation requested: {tool.id}",
        )

        invocation = self._invocations.mark_running_without_event(invocation.id)
        await self._emit_invocation_event(
            EventType.TOOL_INVOCATION_RUNNING,
            invocation,
            message=f"Tool invocation running: {tool.id}",
        )

        try:
            completed = await self._execution.execute_invocation(invocation.id)
        except Exception:
            await self._events.emit_event(
                event_type=EventType.WORK_LOOP_FAILED,
                message=f"Work loop failed: {tool_name}",
                metadata={
                    "session_id": runtime_session.id,
                    "task_id": runtime_session.task_id,
                    "tool_id": tool.id,
                    "tool_name": tool.name,
                    "invocation_id": invocation.id,
                },
            )
            raise

        event_type = (
            EventType.WORK_LOOP_COMPLETED
            if completed.status == "completed"
            else EventType.WORK_LOOP_FAILED
        )
        await self._events.emit_event(
            event_type=event_type,
            message=f"Work loop {completed.status}: {tool_name}",
            metadata={
                "session_id": runtime_session.id,
                "task_id": runtime_session.task_id,
                "tool_id": tool.id,
                "tool_name": tool.name,
                "invocation_id": completed.id,
                "status": completed.status,
            },
        )

        return {
            "session_id": session_id,
            "tool_name": tool_name,
            "invocation_id": completed.id,
            "status": completed.status,
        }

    async def _emit_invocation_event(
        self,
        event_type: EventType,
        invocation,
        message: str,
    ) -> None:
        metadata: dict[str, Any] = {
            "tool_invocation_id": invocation.id,
            "session_id": invocation.session_id,
            "tool_id": invocation.tool_id,
            "status": invocation.status,
            "created_at": invocation.created_at.isoformat(),
        }
        input_payload = self._invocations.input_payload_for(invocation)
        if input_payload is not None:
            metadata["input_payload"] = input_payload

        await self._events.emit_event(
            event_type=event_type,
            message=message,
            metadata=metadata,
        )


work_loop_service = WorkLoopService()
