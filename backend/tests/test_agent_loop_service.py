import json
import subprocess

from app.models.agent_loop import AgentLoopRequest, AgentLoopStatus
from app.models.provider_execution import (
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderMessageRole,
)
from app.models.runtime_event import EventType
from app.services.agent_loop_prompt_builder_service import (
    AGENT_LOOP_SYSTEM_PROMPT,
)
from app.services.agent_loop_service import AgentLoopService
from app.services.agent_tool_registry_service import AgentToolRegistryService
from app.services.event_service import EventService
from app.services.trace_service import TraceService
from app.services.runtime_workspace_service import RuntimeWorkspaceService


class StubProviderExecutionService:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            effective_provider_id=request.provider,
            effective_model=request.model,
            routing_reason="explicit_request",
            routing_source="explicit_request",
            budget_mode=request.metadata.get("budget_mode"),
            task_type=request.metadata.get("task_type"),
            metadata={
                "budget_policy": {
                    "classification": "balanced",
                    "warnings": [],
                    "metadata": {},
                }
            },
            content=self.outputs[len(self.requests) - 1],
        )


def request(max_iterations: int = 5) -> AgentLoopRequest:
    return AgentLoopRequest(
        session_id="loop-session-1",
        user_request="Produce an answer",
        max_iterations=max_iterations,
        workspace_id=None,
        provider_id="fake",
        model="fake-model",
    )


def service(
    tmp_path,
    outputs: list[str],
    tools: AgentToolRegistryService | None = None,
    workspace: RuntimeWorkspaceService | None = None,
) -> tuple[AgentLoopService, StubProviderExecutionService, EventService]:
    provider = StubProviderExecutionService(outputs)
    events = EventService(TraceService(tmp_path / "agent-loop.db"))
    workspace = workspace or RuntimeWorkspaceService(tmp_path)
    return (
        AgentLoopService(
            provider_execution=provider,
            events=events,
            tools=tools,
            workspace=workspace,
        ),
        provider,
        events,
    )


def tool_output(tool: str, arguments: dict[str, str]) -> str:
    return json.dumps({"tool": tool, "arguments": arguments})


def test_loop_completes_on_final_answer(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Done."})],
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.final_answer == "Done."
    assert result.iterations_used == 1
    assert result.steps[0].tool_result is not None
    assert result.steps[0].tool_result.completion_intent is True
    assert len(provider.requests) == 1
    persisted_events = events.list_persisted_events()
    workspace_id = persisted_events[0].metadata["workspace_id"]
    assert [event.type.value for event in persisted_events] == [
        "agent_loop_started",
        "agent_loop_provider_requested",
        "agent_loop_provider_completed",
        "agent_loop_tool_selected",
        "agent_loop_tool_completed",
        "agent_loop_completed",
    ]
    assert [event.metadata for event in persisted_events] == [
        {
            "session_id": "loop-session-1",
            "user_request": "Produce an answer",
            "max_iterations": 5,
            "workspace_id": workspace_id,
            "workspace_root_path": tmp_path.resolve().as_posix(),
            "provider_id": "fake",
            "model": "fake-model",
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "provider_id": "fake",
            "model": "fake-model",
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "status": "completed",
            "provider_id": "fake",
            "model": "fake-model",
            "effective_provider_id": "fake",
            "effective_model": "fake-model",
            "routing_reason": "explicit_request",
            "routing_source": "explicit_request",
            "budget_policy": {
                "classification": "balanced",
                "warnings": [],
                "metadata": {},
            },
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "tool": "final_answer",
            "arguments": {"answer": "Done."},
        },
        {
            "session_id": "loop-session-1",
            "iteration": 1,
            "tool": "final_answer",
            "output": "Done.",
            "completion_intent": True,
            "duration_ms": persisted_events[4].metadata["duration_ms"],
            "success": True,
        },
        {
            "session_id": "loop-session-1",
            "status": "completed",
            "final_answer": "Done.",
            "iterations_used": 1,
        },
    ]
    assert persisted_events[4].metadata["duration_ms"] >= 0


def test_loop_passes_provider_request_through_without_augmentation(tmp_path) -> None:
    loop, provider, _ = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Done."})],
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.COMPLETED
    assert len(provider.requests) == 1
    provider_request = provider.requests[0]
    assert provider_request.provider == "fake"
    assert provider_request.model == "fake-model"
    assert provider_request.metadata["workspace_id"] is not None
    assert provider_request.metadata["source"] == "agent_loop"


def test_loop_provider_completed_event_includes_routing_metadata(tmp_path) -> None:
    loop, _, events = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Done."})],
    )

    loop.run(request())

    provider_completed = [
        event
        for event in events.list_persisted_events()
        if event.type == EventType.AGENT_LOOP_PROVIDER_COMPLETED
    ][0]
    assert provider_completed.metadata["effective_provider_id"] == "fake"
    assert provider_completed.metadata["effective_model"] == "fake-model"
    assert provider_completed.metadata["routing_reason"] == "explicit_request"
    assert provider_completed.metadata["routing_source"] == "explicit_request"
    assert provider_completed.metadata["budget_policy"] == {
        "classification": "balanced",
        "warnings": [],
        "metadata": {},
    }
    assert "api_key" not in provider_completed.metadata


def test_loop_execution_result_includes_budget_policy(tmp_path) -> None:
    loop, provider, _ = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Done."})],
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.COMPLETED
    assert provider.requests[0].metadata["source"] == "agent_loop"


def test_loop_fails_on_invalid_json(tmp_path) -> None:
    loop, _, events = service(tmp_path, ["not JSON"])

    result = loop.run(request())

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 1
    assert "Invalid agent loop provider output" in result.error
    failed_event = events.list_persisted_events()[-1]
    assert failed_event.type.value == "agent_loop_failed"
    assert failed_event.metadata == {
        "session_id": "loop-session-1",
        "status": "failed",
        "error": result.error,
        "iterations_used": 1,
    }


def test_loop_stops_before_provider_call_when_stop_requested(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Not reached"})],
    )
    events.emit_event_sync(
        event_type=EventType.AGENT_LOOP_STOP_REQUESTED,
        message="Agent loop stop requested",
        metadata={
            "session_id": "loop-session-1",
            "reason": "Requested by user",
        },
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.STOPPED
    assert result.iterations_used == 0
    assert provider.requests == []
    stopped_event = events.list_persisted_events()[-1]
    assert stopped_event.type == EventType.AGENT_LOOP_STOPPED
    assert stopped_event.metadata == {
        "session_id": "loop-session-1",
        "status": "stopped",
        "iterations_used": 0,
        "reason": "Requested by user",
    }


def test_loop_fails_on_unknown_tool(tmp_path) -> None:
    loop, _, _ = service(
        tmp_path,
        [tool_output("git", {"command": "unsafe"})],
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 1
    assert result.error == "Unknown agent loop tool: git"


def test_loop_rejected_validation_does_not_emit_tool_completed(tmp_path) -> None:
    loop, _, events = service(
        tmp_path,
        [tool_output("read_file", {"path": "../outside.txt"})],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.FAILED
    assert "outside the workspace" in result.error
    assert not any(
        event.type == EventType.AGENT_LOOP_TOOL_COMPLETED
        for event in events.list_persisted_events()
    )


def test_loop_uses_requested_workspace_id(tmp_path) -> None:
    workspace_service = RuntimeWorkspaceService(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    registered = workspace_service.register_workspace("other", other)
    loop, provider, _ = service(
        tmp_path,
        [tool_output("final_answer", {"answer": "Done."})],
        workspace=workspace_service,
    )

    result = loop.run(
        request().model_copy(update={"workspace_id": registered.workspace_id})
    )

    assert result.status == AgentLoopStatus.COMPLETED
    assert provider.requests[0].metadata["workspace_id"] == registered.workspace_id
    assert provider.requests[0].metadata["workspace_root_path"] == other.resolve().as_posix()


def test_loop_active_workspace_change_does_not_affect_running_session(
    tmp_path,
) -> None:
    workspace_service = RuntimeWorkspaceService(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    registered = workspace_service.register_workspace("other", other)

    class SwitchingProviderExecutionService(StubProviderExecutionService):
        def execute(self, request):
            workspace_service.set_active_workspace(registered.workspace_id)
            return super().execute(request)

    provider = SwitchingProviderExecutionService(
        [tool_output("final_answer", {"answer": "kept"})]
    )
    events = EventService(TraceService(tmp_path / "agent-loop.db"))
    loop = AgentLoopService(
        provider_execution=provider,
        events=events,
        workspace=workspace_service,
    )
    result = loop.run(request().model_copy(update={"workspace_id": None}))

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.final_answer == "kept"
    assert provider.requests[0].metadata["workspace_root_path"] == tmp_path.resolve().as_posix()


def test_loop_respects_max_iterations(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output("observe", {"message": "First observation"}),
            tool_output("observe", {"message": "Second observation"}),
        ],
    )

    result = loop.run(request(max_iterations=2))

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 2
    assert len(result.steps) == 2
    assert len(provider.requests) == 2
    assert result.error == (
        "Agent loop reached max_iterations (2) without a final_answer"
    )
    assert events.list_persisted_events()[-1].metadata == {
        "session_id": "loop-session-1",
        "status": "failed",
        "error": result.error,
        "iterations_used": 2,
    }
    second_messages = provider.requests[1].messages
    assert [
        (message.role, message.content) for message in second_messages
    ] == [
        (ProviderMessageRole.SYSTEM, AGENT_LOOP_SYSTEM_PROMPT),
        (ProviderMessageRole.USER, "Produce an answer"),
        (
            ProviderMessageRole.ASSISTANT,
            tool_output("observe", {"message": "First observation"}),
        ),
        (ProviderMessageRole.USER, "First observation"),
    ]


def test_loop_accumulates_context_for_each_provider_invocation(
    tmp_path,
) -> None:
    outputs = [
        tool_output("observe", {"message": "First observation"}),
        tool_output("observe", {"message": "Second observation"}),
        tool_output("final_answer", {"answer": "Done."}),
    ]
    loop, provider, _ = service(tmp_path, outputs)

    result = loop.run(request(max_iterations=3))

    assert result.status == AgentLoopStatus.COMPLETED
    assert [
        (message.role, message.content)
        for message in provider.requests[2].messages
    ] == [
        (ProviderMessageRole.SYSTEM, AGENT_LOOP_SYSTEM_PROMPT),
        (ProviderMessageRole.USER, "Produce an answer"),
        (ProviderMessageRole.ASSISTANT, outputs[0]),
        (ProviderMessageRole.USER, "First observation"),
        (ProviderMessageRole.ASSISTANT, outputs[1]),
        (ProviderMessageRole.USER, "Second observation"),
    ]


def test_loop_executes_read_file_tool(tmp_path) -> None:
    (tmp_path / "context.txt").write_text(
        "Runtime context",
        encoding="utf-8",
    )
    loop, provider, _ = service(
        tmp_path,
        [
            tool_output("read_file", {"path": "context.txt"}),
            tool_output("final_answer", {"answer": "Read complete."}),
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.steps[0].tool_result is not None
    assert result.steps[0].tool_result.output == "Runtime context"
    assert provider.requests[1].messages[-1].content == "Runtime context"


def test_loop_executes_list_directory_tool(tmp_path) -> None:
    files = tmp_path / "files"
    files.mkdir()
    (files / "zeta.txt").touch()
    (files / "alpha.txt").touch()
    loop, provider, _ = service(
        tmp_path,
        [
            tool_output("list_directory", {"path": "files"}),
            tool_output("final_answer", {"answer": "Listed."}),
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.steps[0].tool_result is not None
    assert json.loads(result.steps[0].tool_result.output) == [
        "alpha.txt",
        "zeta.txt",
    ]
    assert provider.requests[1].messages[-1].content == (
        result.steps[0].tool_result.output
    )


def test_loop_requests_approval_before_write_file(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "write_file",
                {"path": "output.txt", "content": "Approved content"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.PAUSED
    assert len(provider.requests) == 1
    assert not (tmp_path / "output.txt").exists()
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    assert approval.metadata["tool"] == "write_file"
    assert approval.metadata["arguments"] == {
        "path": "output.txt",
        "content": "Approved content",
    }


def test_approved_resume_writes_file_once_without_provider_call(
    tmp_path,
) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "write_file",
                {"path": "output.txt", "content": "First content"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "approved")

    first = loop.resume_approval(approval.metadata["approval_id"])
    (tmp_path / "output.txt").write_text(
        "Changed after resume",
        encoding="utf-8",
    )
    second = loop.resume_approval(approval.metadata["approval_id"])

    assert first.executed is True
    assert json.loads(first.tool_result.output) == {
        "path": "output.txt",
        "bytes_written": 13,
    }
    assert second.executed is False
    assert second.already_resumed is True
    assert (tmp_path / "output.txt").read_text(
        encoding="utf-8"
    ) == "Changed after resume"
    assert len(provider.requests) == 1
    completed = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_TOOL_COMPLETED.value
    )
    assert len(completed) == 1
    assert completed[0].metadata["tool"] == "write_file"


def test_rejected_write_file_approval_does_not_write(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "write_file",
                {"path": "rejected.txt", "content": "Do not write"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "rejected")

    resumed = loop.resume_approval(approval.metadata["approval_id"])

    assert resumed.executed is False
    assert not (tmp_path / "rejected.txt").exists()
    assert len(provider.requests) == 1


def test_continue_after_approved_write_reaches_final_answer(
    tmp_path,
) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "write_file",
                {"path": "continued.txt", "content": "Continue content"},
            ),
            tool_output("final_answer", {"answer": "Write complete."}),
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "approved")

    result = loop.continue_approval(approval.metadata["approval_id"])

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.final_answer == "Write complete."
    assert (tmp_path / "continued.txt").read_text(
        encoding="utf-8"
    ) == "Continue content"
    assert len(provider.requests) == 2
    assert json.loads(provider.requests[1].messages[-1].content) == {
        "path": "continued.txt",
        "bytes_written": 16,
    }


def test_loop_requests_approval_before_run_shell(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "run_shell",
                {"command": "printf executed > marker.txt"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.PAUSED
    assert len(provider.requests) == 1
    assert not (tmp_path / "marker.txt").exists()
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    assert approval.metadata["tool"] == "run_shell"
    assert approval.metadata["arguments"]["command"] == (
        "printf executed > marker.txt"
    )


def test_approved_resume_runs_shell_once_without_provider_call(
    tmp_path,
) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "run_shell",
                {"command": "printf executed >> marker.txt"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "approved")

    first = loop.resume_approval(approval.metadata["approval_id"])
    second = loop.resume_approval(approval.metadata["approval_id"])

    assert first.executed is True
    assert second.executed is False
    assert second.already_resumed is True
    assert (tmp_path / "marker.txt").read_text(
        encoding="utf-8"
    ) == "executed"
    assert len(provider.requests) == 1
    completed = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_TOOL_COMPLETED.value
    )
    assert len(completed) == 1
    assert completed[0].metadata["stdout"] == ""
    assert completed[0].metadata["stderr"] == ""
    assert completed[0].metadata["exit_code"] == 0
    assert completed[0].metadata["success"] is True
    assert completed[0].metadata["duration_ms"] >= 0


def test_rejected_run_shell_approval_does_not_execute(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "run_shell",
                {"command": "printf rejected > rejected.txt"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "rejected")

    resumed = loop.resume_approval(approval.metadata["approval_id"])

    assert resumed.executed is False
    assert not (tmp_path / "rejected.txt").exists()
    assert len(provider.requests) == 1


def test_continue_after_approved_run_shell_reaches_final_answer(
    tmp_path,
) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "run_shell",
                {"command": "printf shell-output"},
            ),
            tool_output("final_answer", {"answer": "Shell complete."}),
        ],
        tools=AgentToolRegistryService(workspace_root=tmp_path),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "approved")

    result = loop.continue_approval(approval.metadata["approval_id"])

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.final_answer == "Shell complete."
    assert len(provider.requests) == 2
    assert json.loads(provider.requests[1].messages[-1].content) == {
        "stdout": "shell-output",
        "stderr": "",
        "exit_code": 0,
    }


def test_git_checkpoint_requests_approval_before_commit(tmp_path) -> None:
    repository = _init_git_repository(tmp_path / "repo")
    (repository / "tracked.txt").write_text("changed", encoding="utf-8")
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "git_checkpoint",
                {"message": "Approved checkpoint"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=repository),
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.PAUSED
    assert len(provider.requests) == 1
    assert _git_commit_count(repository) == 1
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    assert approval.metadata["tool"] == "git_checkpoint"


def test_approved_checkpoint_resume_commits_once(tmp_path) -> None:
    repository = _init_git_repository(tmp_path / "repo")
    (repository / "tracked.txt").write_text("changed", encoding="utf-8")
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "git_checkpoint",
                {"message": "Approved checkpoint"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=repository),
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "approved")

    first = loop.resume_approval(approval.metadata["approval_id"])
    second = loop.resume_approval(approval.metadata["approval_id"])

    assert first.executed is True
    assert second.executed is False
    assert second.already_resumed is True
    assert _git_commit_count(repository) == 2
    assert len(provider.requests) == 1
    assert _git(repository, "log", "-1", "--pretty=%s").stdout.strip() == (
        "Approved checkpoint"
    )
    completed = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_TOOL_COMPLETED.value
    )[-1]
    assert completed.metadata["tool"] == "git_checkpoint"
    assert completed.metadata["commit_hash"] == _git(
        repository,
        "rev-parse",
        "HEAD",
    ).stdout.strip()
    assert completed.metadata["success"] is True


def test_git_create_branch_requests_approval_and_rejection_is_safe(
    tmp_path,
) -> None:
    repository = _init_git_repository(tmp_path / "repo")
    original_branch = _git(
        repository,
        "branch",
        "--show-current",
    ).stdout.strip()
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "git_create_branch",
                {"branch": "runtime/safe-branch"},
            )
        ],
        tools=AgentToolRegistryService(workspace_root=repository),
    )

    paused = loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    _respond_to_approval(events, approval.metadata["approval_id"], "rejected")
    resumed = loop.resume_approval(approval.metadata["approval_id"])

    assert paused.status == AgentLoopStatus.PAUSED
    assert approval.metadata["tool"] == "git_create_branch"
    assert resumed.executed is False
    assert len(provider.requests) == 1
    assert _git(
        repository,
        "branch",
        "--show-current",
    ).stdout.strip() == original_branch
    branches = _git(
        repository,
        "branch",
        "--format=%(refname:short)",
    ).stdout.splitlines()
    assert "runtime/safe-branch" not in branches


def test_loop_pauses_for_approval_without_executing_tool(
    tmp_path,
    monkeypatch,
) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "propose_change",
                {
                    "title": "Update configuration",
                    "description": "Use the safer default.",
                },
            ),
            tool_output("final_answer", {"answer": "Not reached"}),
        ],
    )

    def fail_if_executed(*args, **kwargs):
        raise AssertionError("gated tool must not execute")

    monkeypatch.setattr(
        AgentToolRegistryService,
        "execute",
        fail_if_executed,
    )

    result = loop.run(request())

    assert result.status == AgentLoopStatus.PAUSED
    assert result.iterations_used == 1
    assert len(provider.requests) == 1
    assert result.steps[0].tool_call is not None
    assert result.steps[0].tool_result is None
    approval_event = events.list_persisted_events()[-1]
    assert approval_event.type == EventType.AGENT_LOOP_APPROVAL_REQUESTED
    assert approval_event.metadata == {
        "approval_id": approval_event.metadata["approval_id"],
        "session_id": "loop-session-1",
        "iteration": 1,
        "tool": "propose_change",
        "arguments": {
            "title": "Update configuration",
            "description": "Use the safer default.",
        },
        "status": "pending",
    }


def test_approved_continue_resumes_tool_and_gets_final_answer(
    tmp_path,
) -> None:
    proposal = tool_output(
        "propose_change",
        {
            "title": "Update configuration",
            "description": "Use the safer default.",
        },
    )
    loop, provider, events = service(
        tmp_path,
        [
            proposal,
            tool_output("final_answer", {"answer": "Done."}),
        ],
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    events.emit_event_sync(
        event_type=EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        message="Agent loop approval responded",
        metadata={
            "approval_id": approval.metadata["approval_id"],
            "session_id": request().session_id,
            "status": "approved",
        },
    )

    result = loop.continue_approval(approval.metadata["approval_id"])

    assert result.status == AgentLoopStatus.COMPLETED
    assert result.final_answer == "Done."
    assert result.iterations_used == 2
    assert len(provider.requests) == 2
    assert [
        (message.role, message.content)
        for message in provider.requests[1].messages[-2:]
    ] == [
        (ProviderMessageRole.ASSISTANT, proposal),
        (
            ProviderMessageRole.USER,
            "Update configuration: Use the safer default.",
        ),
    ]
    continue_event = events.list_persisted_events(
        event_type=(
            EventType.AGENT_LOOP_APPROVAL_CONTINUE_STARTED.value
        )
    )[-1]
    assert continue_event.metadata == {
        "approval_id": approval.metadata["approval_id"],
        "session_id": request().session_id,
    }


def test_repeated_continue_does_not_repeat_tool_or_provider(
    tmp_path,
    monkeypatch,
) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "propose_change",
                {"title": "Change", "description": "Once."},
            ),
            tool_output("final_answer", {"answer": "Done."}),
        ],
    )
    loop.run(request())
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    events.emit_event_sync(
        event_type=EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        message="Agent loop approval responded",
        metadata={
            "approval_id": approval.metadata["approval_id"],
            "session_id": request().session_id,
            "status": "approved",
        },
    )
    original_execute = AgentToolRegistryService.execute
    executions = []

    def track_execute(self, tool_call, arguments=None):
        executions.append(tool_call)
        return original_execute(self, tool_call, arguments)

    monkeypatch.setattr(AgentToolRegistryService, "execute", track_execute)

    first = loop.continue_approval(approval.metadata["approval_id"])
    second = loop.continue_approval(approval.metadata["approval_id"])

    assert first.status == AgentLoopStatus.COMPLETED
    assert second.status == AgentLoopStatus.COMPLETED
    assert len(executions) == 2
    assert [call.tool for call in executions] == [
        "propose_change",
        "final_answer",
    ]
    assert len(provider.requests) == 2


def test_continue_respects_original_max_iterations(tmp_path) -> None:
    loop, provider, events = service(
        tmp_path,
        [
            tool_output(
                "propose_change",
                {"title": "Change", "description": "At the limit."},
            )
        ],
    )
    loop.run(request(max_iterations=1))
    approval = events.list_persisted_events(
        event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
    )[-1]
    events.emit_event_sync(
        event_type=EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        message="Agent loop approval responded",
        metadata={
            "approval_id": approval.metadata["approval_id"],
            "session_id": request().session_id,
            "status": "approved",
        },
    )

    result = loop.continue_approval(approval.metadata["approval_id"])

    assert result.status == AgentLoopStatus.FAILED
    assert result.iterations_used == 1
    assert result.error == (
        "Agent loop reached max_iterations (1) without a final_answer"
    )
    assert len(provider.requests) == 1


def _respond_to_approval(
    events: EventService,
    approval_id: str,
    status: str,
) -> None:
    events.emit_event_sync(
        event_type=EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        message="Agent loop approval responded",
        metadata={
            "approval_id": approval_id,
            "session_id": request().session_id,
            "status": status,
        },
    )


def _init_git_repository(path):
    path.mkdir()
    _git(path, "init", "--quiet")
    _git(path, "config", "user.name", "Stratum Test")
    _git(path, "config", "user.email", "stratum@example.test")
    (path / "tracked.txt").write_text("initial", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "--quiet", "-m", "Initial")
    return path


def _git(path, *arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )


def _git_commit_count(path) -> int:
    return int(_git(path, "rev-list", "--count", "HEAD").stdout.strip())
