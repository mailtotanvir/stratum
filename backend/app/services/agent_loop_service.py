import json

from pydantic import ValidationError

from app.models.agent_loop import (
    AgentLoopRequest,
    AgentLoopResult,
    AgentLoopStatus,
    AgentLoopStep,
    AgentLoopToolCall,
)
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRecord,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.models.runtime_event import EventType, Severity
from app.services.agent_loop_prompt_builder_service import (
    AgentLoopPromptBuilderService,
)
from app.services.agent_tool_registry_service import (
    AgentToolRegistryService,
    agent_tool_registry_service,
)
from app.services.event_service import EventService, event_service
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service_default,
)


DEFAULT_PROVIDER_ID = "mock"
DEFAULT_MODEL = "mock-small"


class AgentLoopService:
    def __init__(
        self,
        provider_execution: ProviderExecutionService | None = None,
        events: EventService | None = None,
        tools: AgentToolRegistryService | None = None,
        prompt_builder: AgentLoopPromptBuilderService | None = None,
    ) -> None:
        self._events = events if events is not None else event_service
        self._provider_execution = (
            provider_execution
            if provider_execution is not None
            else provider_execution_service_default(events=self._events)
        )
        self._tools = (
            tools if tools is not None else agent_tool_registry_service
        )
        self._prompt_builder = (
            prompt_builder
            if prompt_builder is not None
            else AgentLoopPromptBuilderService(self._tools)
        )

    def run(self, request: AgentLoopRequest) -> AgentLoopResult:
        provider_id = request.provider_id or DEFAULT_PROVIDER_ID
        model = request.model or DEFAULT_MODEL
        steps: list[AgentLoopStep] = []
        self._emit(
            EventType.AGENT_LOOP_STARTED,
            "Agent loop started",
            session_id=request.session_id,
            user_request=request.user_request,
            max_iterations=request.max_iterations,
            provider_id=provider_id,
            model=model,
        )

        for iteration in range(1, request.max_iterations + 1):
            stop_reason = self._stop_reason(request.session_id)
            if stop_reason is not _NO_STOP_REQUEST:
                return self._stopped(
                    request,
                    steps,
                    iteration - 1,
                    stop_reason,
                )
            self._emit(
                EventType.AGENT_LOOP_PROVIDER_REQUESTED,
                "Agent loop provider requested",
                session_id=request.session_id,
                iteration=iteration,
                provider_id=provider_id,
                model=model,
            )
            try:
                provider_response = self._provider_execution.execute(
                    ProviderExecutionRequest(
                        provider=provider_id,
                        model=model,
                        mode=ProviderExecutionMode.TOOL_CALL,
                        messages=self._prompt_builder.build(request, steps),
                        runtime_session_id=request.session_id,
                        metadata={
                            "source": "agent_loop",
                            "iteration": iteration,
                        },
                    )
                )
                provider_result = _provider_result(provider_response)
            except Exception as exc:
                return self._failed(
                    request,
                    steps,
                    iteration,
                    f"Provider execution raised {type(exc).__name__}: {exc}",
                )

            self._emit(
                EventType.AGENT_LOOP_PROVIDER_COMPLETED,
                "Agent loop provider completed",
                session_id=request.session_id,
                iteration=iteration,
                status=provider_result.status.value,
                provider_id=provider_id,
                model=model,
            )
            if provider_result.status != ProviderExecutionStatus.COMPLETED:
                error = (
                    provider_result.error_message
                    or "Provider execution did not complete successfully"
                )
                steps.append(AgentLoopStep(iteration=iteration, error=error))
                return self._failed(
                    request,
                    steps,
                    iteration,
                    error,
                )

            provider_output = provider_result.content
            if provider_output is None:
                error = "Provider returned no content"
                steps.append(AgentLoopStep(iteration=iteration, error=error))
                return self._failed(
                    request,
                    steps,
                    iteration,
                    error,
                )

            try:
                tool_call = _parse_tool_call(provider_output)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                error = f"Invalid agent loop provider output: {exc}"
                steps.append(
                    AgentLoopStep(
                        iteration=iteration,
                        provider_output=provider_output,
                        error=error,
                    )
                )
                return self._failed(
                    request,
                    steps,
                    iteration,
                    error,
                )

            self._emit(
                EventType.AGENT_LOOP_TOOL_SELECTED,
                "Agent loop tool selected",
                session_id=request.session_id,
                iteration=iteration,
                tool=tool_call.tool,
                arguments=tool_call.arguments,
            )
            try:
                tool_result = self._tools.execute(tool_call)
            except ValueError as exc:
                error = str(exc)
                steps.append(
                    AgentLoopStep(
                        iteration=iteration,
                        provider_output=provider_output,
                        tool_call=tool_call,
                        error=error,
                    )
                )
                return self._failed(
                    request,
                    steps,
                    iteration,
                    error,
                )

            step = AgentLoopStep(
                iteration=iteration,
                provider_output=provider_output,
                tool_call=tool_call,
                tool_result=tool_result,
            )
            steps.append(step)
            self._emit(
                EventType.AGENT_LOOP_TOOL_COMPLETED,
                "Agent loop tool completed",
                session_id=request.session_id,
                iteration=iteration,
                tool=tool_call.tool,
                output=tool_result.output,
                completion_intent=tool_result.completion_intent,
            )

            if tool_result.completion_intent:
                result = AgentLoopResult(
                    session_id=request.session_id,
                    status=AgentLoopStatus.COMPLETED,
                    final_answer=tool_result.output,
                    iterations_used=iteration,
                    steps=steps,
                )
                self._emit(
                    EventType.AGENT_LOOP_COMPLETED,
                    "Agent loop completed",
                    session_id=request.session_id,
                    status=AgentLoopStatus.COMPLETED,
                    final_answer=result.final_answer,
                    iterations_used=result.iterations_used,
                )
                return result

        return self._failed(
            request,
            steps,
            request.max_iterations,
            (
                "Agent loop reached max_iterations "
                f"({request.max_iterations}) without a final_answer"
            ),
        )

    def _failed(
        self,
        request: AgentLoopRequest,
        steps: list[AgentLoopStep],
        iterations_used: int,
        error: str,
    ) -> AgentLoopResult:
        self._emit(
            EventType.AGENT_LOOP_FAILED,
            "Agent loop failed",
            session_id=request.session_id,
            status=AgentLoopStatus.FAILED,
            error=error,
            iterations_used=iterations_used,
            severity=Severity.ERROR,
        )
        return AgentLoopResult(
            session_id=request.session_id,
            status=AgentLoopStatus.FAILED,
            iterations_used=iterations_used,
            steps=steps,
            error=error,
        )

    def _stop_reason(self, session_id: str) -> object:
        for event in reversed(
            self._events.list_persisted_events(
                event_type=EventType.AGENT_LOOP_STOP_REQUESTED.value
            )
        ):
            if event.metadata.get("session_id") == session_id:
                return event.metadata.get("reason")
        return _NO_STOP_REQUEST

    def _stopped(
        self,
        request: AgentLoopRequest,
        steps: list[AgentLoopStep],
        iterations_used: int,
        reason: object,
    ) -> AgentLoopResult:
        payload: dict[str, object] = {
            "session_id": request.session_id,
            "status": AgentLoopStatus.STOPPED,
            "iterations_used": iterations_used,
        }
        if reason is not None:
            payload["reason"] = reason
        self._emit(
            EventType.AGENT_LOOP_STOPPED,
            "Agent loop stopped",
            **payload,
        )
        return AgentLoopResult(
            session_id=request.session_id,
            status=AgentLoopStatus.STOPPED,
            iterations_used=iterations_used,
            steps=steps,
        )

    def _emit(
        self,
        event_type: EventType,
        message: str,
        *,
        severity: Severity = Severity.INFO,
        **payload: object,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            message=message,
            severity=severity,
            metadata={
                key: value.value
                if isinstance(value, AgentLoopStatus)
                else value
                for key, value in payload.items()
            },
        )


_NO_STOP_REQUEST = object()


def _provider_result(
    response: ProviderExecutionRecord | ProviderExecutionResult,
) -> ProviderExecutionResult:
    if isinstance(response, ProviderExecutionResult):
        return response
    if response.result is None:
        raise ValueError("Provider execution returned no result")
    return response.result


def _parse_tool_call(provider_output: str) -> AgentLoopToolCall:
    payload = json.loads(provider_output)
    if not isinstance(payload, dict):
        raise ValueError("provider output must be a JSON object")
    if set(payload) != {"tool", "arguments"}:
        raise ValueError(
            "provider output must contain exactly 'tool' and 'arguments'"
        )
    if not isinstance(payload["arguments"], dict):
        raise ValueError("'arguments' must be a JSON object")
    return AgentLoopToolCall.model_validate(payload)
