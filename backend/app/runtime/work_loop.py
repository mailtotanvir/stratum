import asyncio
import hashlib
import json
from typing import Any

from app.models.agent_execution import (
    AgentExecutionMode,
    AgentExecutionRequest,
    AgentExecutionStatus,
)
from app.models.provider_execution import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.models.runtime_event import EventType
from app.services.agent_execution_service import AgentExecutionService
from app.services.event_service import EventService, event_service
from app.services.provider_execution_service import ProviderExecutionService
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
        agent_execution: AgentExecutionService | None = None,
        provider: str = "mock",
        model: str = "mock-small",
        temperature: float | None = None,
    ) -> None:
        self._sessions = sessions or runtime_session_service
        self._tools = tools or tool_registry_service
        self._invocations = invocations or tool_invocation_service
        self._execution = execution or tool_execution_service
        self._events = events or event_service
        self._agent_execution = agent_execution or AgentExecutionService(
            provider_execution=ProviderExecutionService(events=self._events),
            events=self._events,
        )
        self._provider = provider
        self._model = model
        self._temperature = temperature

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

        agent_record = None
        if completed.status == "completed":
            agent_record = await asyncio.to_thread(
                self._agent_execution.execute,
                self._agent_request(
                    runtime_session=runtime_session,
                    tool=tool,
                    input_payload=input_payload,
                ),
            )

        work_status = completed.status
        if (
            agent_record is not None
            and agent_record.status != AgentExecutionStatus.COMPLETED
        ):
            work_status = "failed"

        event_type = (
            EventType.WORK_LOOP_COMPLETED
            if work_status == "completed"
            else EventType.WORK_LOOP_FAILED
        )
        event_metadata = {
            "session_id": runtime_session.id,
            "task_id": runtime_session.task_id,
            "tool_id": tool.id,
            "tool_name": tool.name,
            "invocation_id": completed.id,
            "status": work_status,
        }
        if agent_record is not None:
            event_metadata["agent_execution_id"] = agent_record.id
            if (
                agent_record.result is not None
                and agent_record.result.provider_execution_record_id
                is not None
            ):
                event_metadata["provider_execution_id"] = (
                    agent_record.result.provider_execution_record_id
                )
        await self._events.emit_event(
            event_type=event_type,
            message=f"Work loop {work_status}: {tool_name}",
            metadata=event_metadata,
        )

        result = {
            "session_id": session_id,
            "tool_name": tool_name,
            "invocation_id": completed.id,
            "status": work_status,
        }
        if agent_record is not None:
            result["agent_execution_id"] = agent_record.id
            if (
                agent_record.result is not None
                and agent_record.result.provider_execution_record_id
                is not None
            ):
                result["provider_execution_id"] = (
                    agent_record.result.provider_execution_record_id
                )
        return result

    def _agent_request(
        self,
        runtime_session,
        tool,
        input_payload: dict | None,
    ) -> AgentExecutionRequest:
        correlation_id = _work_correlation_id(
            runtime_session.id,
            runtime_session.task_id,
            tool.id,
            input_payload,
        )
        return AgentExecutionRequest(
            runtime_session_id=runtime_session.id,
            task_id=runtime_session.task_id,
            provider=self._provider,
            model=self._model,
            mode=AgentExecutionMode.SINGLE_TURN,
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content=(
                        f"Runtime session: {runtime_session.id}\n"
                        f"Task: {runtime_session.task_id}\n"
                        f"Selected tool: {tool.name}"
                    ),
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content=json.dumps(
                        {
                            "tool_name": tool.name,
                            "input_payload": input_payload or {},
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            ],
            temperature=self._temperature,
            stream_mode=ProviderStreamMode.NONE,
            correlation_id=correlation_id,
            metadata={
                "source": "runtime_work_loop",
                "tool_id": tool.id,
                "tool_name": tool.name,
            },
        )

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


def _work_correlation_id(
    session_id: str,
    task_id: str,
    tool_id: str,
    input_payload: dict | None,
) -> str:
    payload = json.dumps(
        {
            "session_id": session_id,
            "task_id": task_id,
            "tool_id": tool_id,
            "input_payload": input_payload or {},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"work-loop-{digest}"


work_loop_service = WorkLoopService()
