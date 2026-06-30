import json
from time import monotonic_ns
from uuid import uuid4

from pydantic import ValidationError

from app.models.agent_loop import (
    AgentLoopApprovalResumeResult,
    AgentLoopApprovalStatus,
    AgentLoopRequest,
    AgentLoopResult,
    AgentLoopStatus,
    AgentLoopStep,
    AgentLoopToolCall,
    AgentLoopToolResult,
)
from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRecord,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.services.agent_loop_prompt_builder_service import (
    AgentLoopPromptBuilderService,
)
from app.services.agent_tool_registry_service import (
    AgentToolRegistryService,
)
from app.services.event_service import EventService, event_service
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service_default,
)
from app.services.runtime_workspace_service import (
    RuntimeWorkspaceService,
    runtime_workspace_service,
)


DEFAULT_PROVIDER_ID = "mock"
DEFAULT_MODEL = "mock-small"


class AgentLoopService:
    def __init__(
        self,
        provider_execution: ProviderExecutionService | None = None,
        events: EventService | None = None,
        tools: AgentToolRegistryService | None = None,
        workspace: RuntimeWorkspaceService | None = None,
        prompt_builder: AgentLoopPromptBuilderService | None = None,
    ) -> None:
        self._events = events if events is not None else event_service
        self._provider_execution = (
            provider_execution
            if provider_execution is not None
            else provider_execution_service_default(events=self._events)
        )
        self._tools = tools
        self._workspace = workspace if workspace is not None else runtime_workspace_service
        self._prompt_builder = prompt_builder

    def run(self, request: AgentLoopRequest) -> AgentLoopResult:
        workspace, workspace_id, workspace_root_path = self._resolve_workspace(
            request
        )
        tools = self._tools_for_workspace(workspace)
        prompt_builder = AgentLoopPromptBuilderService(tools)
        return self._run_iterations(
            request,
            [],
            1,
            tools=tools,
            prompt_builder=prompt_builder,
            workspace_id=workspace_id,
            workspace_root_path=workspace_root_path,
            emit_started=True,
        )

    def _run_iterations(
        self,
        request: AgentLoopRequest,
        steps: list[AgentLoopStep],
        start_iteration: int,
        *,
        tools: AgentToolRegistryService,
        prompt_builder: AgentLoopPromptBuilderService,
        workspace_id: str,
        workspace_root_path: str,
        emit_started: bool = False,
    ) -> AgentLoopResult:
        provider_id = request.provider_id or DEFAULT_PROVIDER_ID
        model = request.model or DEFAULT_MODEL
        if emit_started:
            self._emit(
                EventType.AGENT_LOOP_STARTED,
                "Agent loop started",
                session_id=request.session_id,
                user_request=request.user_request,
                max_iterations=request.max_iterations,
                workspace_id=workspace_id,
                workspace_root_path=workspace_root_path,
                provider_id=provider_id,
                model=model,
            )

        for iteration in range(
            start_iteration,
            request.max_iterations + 1,
        ):
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
                        messages=prompt_builder.build(request, steps),
                        runtime_session_id=request.session_id,
                        metadata={
                            "source": "agent_loop",
                            "iteration": iteration,
                            "workspace_id": workspace_id,
                            "workspace_root_path": workspace_root_path,
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
                **_provider_routing_metadata(provider_result),
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
                tools.validate(tool_call)
                tool_definition = tools.get_tool(tool_call.tool)
                if tool_definition.requires_approval:
                    steps.append(
                        AgentLoopStep(
                            iteration=iteration,
                            provider_output=provider_output,
                            tool_call=tool_call,
                        )
                    )
                    approval_id = str(uuid4())
                    self._emit(
                        EventType.AGENT_LOOP_APPROVAL_REQUESTED,
                        "Agent loop approval requested",
                        approval_id=approval_id,
                        session_id=request.session_id,
                        iteration=iteration,
                        tool=tool_call.tool,
                        arguments=tool_call.arguments,
                        status=AgentLoopApprovalStatus.PENDING.value,
                    )
                    return AgentLoopResult(
                        session_id=request.session_id,
                        status=AgentLoopStatus.PAUSED,
                        iterations_used=iteration,
                        steps=steps,
                    )
                tool_started_at = monotonic_ns()
                tool_result = tools.execute(tool_call)
                tool_duration_ms = _duration_ms(tool_started_at)
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
                **_tool_completion_metadata(
                    tool_result,
                    tool_duration_ms,
                ),
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

    def continue_approval(
        self,
        approval_id: str,
    ) -> AgentLoopResult | AgentLoopApprovalResumeResult:
        approval = self._find_approval_event(approval_id)
        if approval is None:
            raise AgentLoopApprovalNotFoundError(approval_id)

        response = self._find_approval_event(
            approval_id,
            EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        )
        if response is None:
            raise AgentLoopApprovalPendingError(approval_id)

        metadata = approval.metadata
        session_id = metadata["session_id"]
        self._emit(
            EventType.AGENT_LOOP_APPROVAL_CONTINUE_STARTED,
            "Agent loop approval continue started",
            approval_id=approval_id,
            session_id=session_id,
        )

        status = AgentLoopApprovalStatus(response.metadata["status"])
        if status == AgentLoopApprovalStatus.REJECTED:
            return self.resume_approval(approval_id)

        resume_result = self.resume_approval(approval_id)

        events = self._session_events(session_id)
        terminal = self._terminal_result(events)
        if terminal is not None:
            return terminal

        started = next(
            (
                event
                for event in reversed(events)
                if event.type == EventType.AGENT_LOOP_STARTED
            ),
            None,
        )
        if started is None:
            raise AgentLoopRunNotFoundError(session_id)

        request = AgentLoopRequest(
            session_id=session_id,
            user_request=started.metadata["user_request"],
            max_iterations=started.metadata["max_iterations"],
            workspace_id=started.metadata.get("workspace_id"),
            provider_id=started.metadata.get("provider_id"),
            model=started.metadata.get("model"),
        )
        workspace = self._workspace_from_started_event(started)
        tools = self._tools_for_workspace(workspace)
        steps = self._reconstruct_steps(events)
        if resume_result.tool_result is not None and not any(
            step.iteration == metadata["iteration"]
            and step.tool_result is not None
            for step in steps
        ):
            steps.append(
                AgentLoopStep(
                    iteration=metadata["iteration"],
                    provider_output=json.dumps(
                        {
                            "tool": metadata["tool"],
                            "arguments": metadata["arguments"],
                        }
                    ),
                    tool_call=AgentLoopToolCall(
                        tool=metadata["tool"],
                        arguments=metadata["arguments"],
                    ),
                    tool_result=resume_result.tool_result,
                )
            )
        steps.sort(key=lambda step: step.iteration)
        return self._run_iterations(
            request,
            steps,
            metadata["iteration"] + 1,
            tools=tools,
            prompt_builder=AgentLoopPromptBuilderService(tools),
            workspace_id=started.metadata["workspace_id"],
            workspace_root_path=started.metadata["workspace_root_path"],
        )

    def resume_approval(
        self,
        approval_id: str,
    ) -> AgentLoopApprovalResumeResult:
        approval = self._find_approval_event(approval_id)
        if approval is None:
            raise AgentLoopApprovalNotFoundError(approval_id)

        completed = self._find_approval_event(
            approval_id,
            EventType.AGENT_LOOP_TOOL_COMPLETED,
        )
        resumed = self._find_approval_event(
            approval_id,
            EventType.AGENT_LOOP_APPROVAL_RESUMED,
        )
        if resumed is not None or completed is not None:
            return self._already_resumed_result(approval, completed)

        response = self._find_approval_event(
            approval_id,
            EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        )
        if response is None:
            raise AgentLoopApprovalPendingError(approval_id)

        metadata = approval.metadata
        status = AgentLoopApprovalStatus(response.metadata["status"])
        reason = response.metadata.get("reason")
        if status == AgentLoopApprovalStatus.REJECTED:
            payload: dict[str, object] = {
                "approval_id": approval_id,
                "session_id": metadata["session_id"],
            }
            if reason is not None:
                payload["reason"] = reason
            self._emit(
                EventType.AGENT_LOOP_APPROVAL_RESUME_REJECTED,
                "Agent loop approval resume rejected",
                **payload,
            )
            return AgentLoopApprovalResumeResult(
                approval_id=approval_id,
                session_id=metadata["session_id"],
                status=status,
                tool=metadata["tool"],
                executed=False,
                reason=reason,
            )

        tool_call = AgentLoopToolCall(
            tool=metadata["tool"],
            arguments=metadata["arguments"],
        )
        workspace = self._workspace_from_session(metadata["session_id"])
        tools = self._tools_for_workspace(workspace)
        tools.validate(tool_call)
        self._emit(
            EventType.AGENT_LOOP_APPROVAL_RESUMED,
            "Agent loop approval resumed",
            approval_id=approval_id,
            session_id=metadata["session_id"],
            iteration=metadata["iteration"],
            tool=metadata["tool"],
        )
        tool_started_at = monotonic_ns()
        tool_result = tools.execute(tool_call)
        tool_duration_ms = _duration_ms(tool_started_at)
        self._emit(
            EventType.AGENT_LOOP_TOOL_COMPLETED,
            "Agent loop tool completed",
            approval_id=approval_id,
            session_id=metadata["session_id"],
            iteration=metadata["iteration"],
            tool=metadata["tool"],
            **_tool_completion_metadata(
                tool_result,
                tool_duration_ms,
            ),
        )
        return AgentLoopApprovalResumeResult(
            approval_id=approval_id,
            session_id=metadata["session_id"],
            status=status,
            tool=metadata["tool"],
            executed=True,
            tool_result=tool_result,
        )

    def _session_events(self, session_id: str) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.metadata.get("session_id") == session_id
            and event.type.value.startswith("agent_loop_")
        ]

    @staticmethod
    def _reconstruct_steps(
        events: list[RuntimeEvent],
    ) -> list[AgentLoopStep]:
        steps: dict[int, AgentLoopStep] = {}
        for event in events:
            iteration = event.metadata.get("iteration")
            if not isinstance(iteration, int):
                continue
            if event.type == EventType.AGENT_LOOP_TOOL_SELECTED:
                tool_call = AgentLoopToolCall(
                    tool=event.metadata["tool"],
                    arguments=event.metadata["arguments"],
                )
                steps[iteration] = AgentLoopStep(
                    iteration=iteration,
                    provider_output=json.dumps(
                        {
                            "tool": tool_call.tool,
                            "arguments": tool_call.arguments,
                        }
                    ),
                    tool_call=tool_call,
                )
            elif event.type == EventType.AGENT_LOOP_TOOL_COMPLETED:
                step = steps.get(iteration)
                if step is None:
                    continue
                step.tool_result = AgentLoopToolResult(
                    tool=event.metadata["tool"],
                    output=event.metadata["output"],
                    completion_intent=event.metadata.get(
                        "completion_intent",
                        False,
                    ),
                    event_metadata=_result_event_metadata(event.metadata),
                )
        return list(steps.values())

    def _terminal_result(
        self,
        events: list[RuntimeEvent],
    ) -> AgentLoopResult | None:
        steps = self._reconstruct_steps(events)
        for event in reversed(events):
            metadata = event.metadata
            if event.type == EventType.AGENT_LOOP_COMPLETED:
                return AgentLoopResult(
                    session_id=metadata["session_id"],
                    status=AgentLoopStatus.COMPLETED,
                    final_answer=metadata.get("final_answer"),
                    iterations_used=metadata["iterations_used"],
                    steps=steps,
                )
            if event.type == EventType.AGENT_LOOP_FAILED:
                return AgentLoopResult(
                    session_id=metadata["session_id"],
                    status=AgentLoopStatus.FAILED,
                    iterations_used=metadata["iterations_used"],
                    steps=steps,
                    error=metadata.get("error"),
                )
            if event.type == EventType.AGENT_LOOP_STOPPED:
                return AgentLoopResult(
                    session_id=metadata["session_id"],
                    status=AgentLoopStatus.STOPPED,
                    iterations_used=metadata["iterations_used"],
                    steps=steps,
                )
        return None

    def _find_approval_event(
        self,
        approval_id: str,
        event_type: EventType = EventType.AGENT_LOOP_APPROVAL_REQUESTED,
    ) -> RuntimeEvent | None:
        for event in reversed(
            self._events.list_persisted_events(
                event_type=event_type.value
            )
        ):
            if event.metadata.get("approval_id") == approval_id:
                return event
        return None

    @staticmethod
    def _already_resumed_result(
        approval: RuntimeEvent,
        completed: RuntimeEvent | None,
    ) -> AgentLoopApprovalResumeResult:
        metadata = approval.metadata
        tool_result: AgentLoopToolResult | None = None
        if completed is not None:
            tool_result = AgentLoopToolResult(
                tool=completed.metadata["tool"],
                output=completed.metadata["output"],
                completion_intent=completed.metadata.get(
                    "completion_intent",
                    False,
                ),
                event_metadata=_result_event_metadata(
                    completed.metadata
                ),
            )
        return AgentLoopApprovalResumeResult(
            approval_id=metadata["approval_id"],
            session_id=metadata["session_id"],
            status=AgentLoopApprovalStatus.APPROVED,
            tool=metadata["tool"],
            executed=False,
            already_resumed=True,
            tool_result=tool_result,
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

    def _resolve_workspace(
        self,
        request: AgentLoopRequest,
    ) -> tuple[RuntimeWorkspaceService, str, str]:
        if request.workspace_id is None:
            active = self._workspace.get_active_workspace()
            return (
                RuntimeWorkspaceService(active.root_path),
                active.workspace_id,
                active.root_path,
            )
        try:
            workspace = self._workspace.get_workspace(request.workspace_id)
        except ValueError as exc:
            raise AgentLoopWorkspaceNotFoundError(
                request.workspace_id
            ) from exc
        return (
            RuntimeWorkspaceService(workspace.root_path),
            workspace.workspace_id,
            workspace.root_path,
        )

    def _workspace_from_session(
        self,
        session_id: str,
    ) -> RuntimeWorkspaceService:
        started = next(
            (
                event
                for event in reversed(self._session_events(session_id))
                if event.type == EventType.AGENT_LOOP_STARTED
            ),
            None,
        )
        if started is None:
            raise ValueError(f"Agent loop run not found: {session_id}")
        workspace_root_path = started.metadata.get("workspace_root_path")
        if not isinstance(workspace_root_path, str):
            raise ValueError("Agent loop run is missing workspace binding")
        return RuntimeWorkspaceService(workspace_root_path)

    def _workspace_from_started_event(
        self,
        started: RuntimeEvent,
    ) -> RuntimeWorkspaceService:
        workspace_root_path = started.metadata.get("workspace_root_path")
        if not isinstance(workspace_root_path, str):
            raise ValueError("Agent loop run is missing workspace binding")
        return RuntimeWorkspaceService(workspace_root_path)

    def _tools_for_workspace(
        self,
        workspace: RuntimeWorkspaceService,
    ) -> AgentToolRegistryService:
        if self._tools is not None:
            return self._tools
        return AgentToolRegistryService(workspace=workspace)

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


def _duration_ms(started_at_ns: int) -> int:
    return max(0, (monotonic_ns() - started_at_ns) // 1_000_000)


def _tool_completion_metadata(
    result: AgentLoopToolResult,
    duration_ms: int,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "output": result.output,
        "completion_intent": result.completion_intent,
        "duration_ms": duration_ms,
        "success": True,
    }
    metadata.update(result.event_metadata)
    return metadata


def _result_event_metadata(
    metadata: dict,
) -> dict[str, object]:
    return {
        key: metadata[key]
        for key in ("stdout", "stderr", "exit_code", "success")
        if key in metadata
    }


_NO_STOP_REQUEST = object()


class AgentLoopApprovalNotFoundError(ValueError):
    pass


class AgentLoopApprovalPendingError(ValueError):
    pass


class AgentLoopRunNotFoundError(ValueError):
    pass


class AgentLoopWorkspaceNotFoundError(ValueError):
    def __init__(self, workspace_id: str) -> None:
        super().__init__(f"Unknown runtime workspace: {workspace_id}")


def _provider_result(
    response: ProviderExecutionRecord | ProviderExecutionResult,
) -> ProviderExecutionResult:
    if isinstance(response, ProviderExecutionResult):
        return response
    if response.result is None:
        raise ValueError("Provider execution returned no result")
    return response.result


def _provider_routing_metadata(
    result: ProviderExecutionResult,
) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in (
        "effective_provider_id",
        "effective_model",
        "routing_reason",
        "routing_source",
        "budget_mode",
        "task_type",
    ):
        value = getattr(result, key, None)
        if value is not None:
            metadata[key] = value
    if "budget_policy" in result.metadata:
        metadata["budget_policy"] = result.metadata["budget_policy"]
    return metadata


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
