import json
import subprocess

import pytest

from app.models.agent_loop import AgentLoopToolCall
from app.services.agent_tool_registry_service import AgentToolRegistryService
from app.services.runtime_workspace_artifact_service import (
    RuntimeWorkspaceArtifactService,
)
from app.services.runtime_workspace_service import RuntimeWorkspaceService


def test_observe_tool_returns_observation() -> None:
    result = AgentToolRegistryService().execute(
        AgentLoopToolCall(
            tool="observe",
            arguments={"message": "The input is valid."},
        )
    )

    assert result.tool == "observe"
    assert result.output == "The input is valid."
    assert result.completion_intent is False


def test_final_answer_tool_marks_completion() -> None:
    result = AgentToolRegistryService().execute(
        "final_answer",
        {"answer": "The final response."},
    )

    assert result.output == "The final response."
    assert result.completion_intent is True


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown agent loop tool"):
        AgentToolRegistryService().execute("shell", {"command": "pwd"})


def test_workspace_boundary_accepts_relative_path(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)

    assert workspace.validate_relative_path("file.txt") == (
        tmp_path / "file.txt"
    )


def test_workspace_boundary_rejects_absolute_path(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)

    with pytest.raises(ValueError, match="must be relative"):
        workspace.validate_relative_path(str(tmp_path / "file.txt"))


def test_workspace_boundary_rejects_traversal(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = RuntimeWorkspaceService(root)

    with pytest.raises(ValueError, match="outside the workspace"):
        workspace.validate_relative_path("../outside.txt")


def test_workspace_boundary_accepts_nested_safe_path(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)

    assert workspace.validate_relative_path(
        "nested/deeper/file.txt"
    ) == (tmp_path / "nested" / "deeper" / "file.txt")


def test_tool_definitions_are_deterministic_and_self_describing() -> None:
    registry = AgentToolRegistryService()

    tools = registry.list_tools()

    assert [tool.name for tool in tools] == [
        "final_answer",
        "git_checkpoint",
        "git_create_branch",
        "git_status",
        "list_directory",
        "observe",
        "propose_change",
        "read_file",
        "run_shell",
        "write_file",
    ]
    by_name = {tool.name: tool for tool in tools}
    assert by_name["final_answer"].argument_schema["properties"]["answer"] == {
        "type": "string"
    }
    assert by_name["final_answer"].argument_schema["required"] == ["answer"]
    assert (
        by_name["final_answer"].argument_schema["additionalProperties"]
        is False
    )
    assert by_name["final_answer"].completion_tool is True
    assert by_name["observe"].argument_schema["properties"]["message"] == {
        "type": "string"
    }
    assert by_name["observe"].argument_schema["required"] == ["message"]
    assert by_name["observe"].completion_tool is False
    assert by_name["propose_change"].argument_schema["properties"] == {
        "title": {"type": "string"},
        "description": {"type": "string"},
    }
    assert by_name["propose_change"].argument_schema["required"] == [
        "title",
        "description",
    ]
    assert by_name["propose_change"].completion_tool is False
    assert by_name["propose_change"].requires_approval is True
    assert by_name["read_file"].argument_schema["required"] == ["path"]
    assert by_name["list_directory"].argument_schema["required"] == ["path"]
    assert by_name["write_file"].argument_schema["required"] == [
        "path",
        "content",
    ]
    assert by_name["write_file"].requires_approval is True
    assert by_name["run_shell"].argument_schema["required"] == ["command"]
    assert by_name["run_shell"].requires_approval is True
    assert by_name["git_status"].requires_approval is False
    assert by_name["git_checkpoint"].requires_approval is True
    assert by_name["git_create_branch"].requires_approval is True
    assert registry.get_tool("observe") == by_name["observe"]


@pytest.mark.parametrize(
    ("tool", "requires_approval"),
    [
        ("observe", False),
        ("final_answer", False),
        ("read_file", False),
        ("list_directory", False),
        ("git_status", False),
        ("propose_change", True),
        ("write_file", True),
        ("run_shell", True),
        ("git_checkpoint", True),
        ("git_create_branch", True),
    ],
)
def test_approval_flags_are_explicit_on_every_tool(
    tool: str,
    requires_approval: bool,
) -> None:
    definition = AgentToolRegistryService().get_tool(tool)

    assert definition.requires_approval is requires_approval


@pytest.mark.parametrize(
    "tool_call",
    [
        AgentLoopToolCall(
            tool="observe",
            arguments={"message": "Observation"},
        ),
        AgentLoopToolCall(
            tool="read_file",
            arguments={"path": "notes.txt"},
        ),
        AgentLoopToolCall(
            tool="list_directory",
            arguments={"path": "."},
        ),
    ],
)
def test_readonly_tool_results_have_stable_shape(
    tmp_path,
    tool_call: AgentLoopToolCall,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if tool_call.tool == "read_file":
        (workspace / "notes.txt").write_text("Notes", encoding="utf-8")

    result = AgentToolRegistryService(workspace_root=workspace).execute(
        tool_call
    )

    assert set(result.model_dump()) == {
        "tool",
        "output",
        "completion_intent",
    }
    assert result.tool == tool_call.tool
    assert isinstance(result.output, str)
    assert result.completion_intent is False


def test_completion_tool_result_shape_is_stable() -> None:
    result = AgentToolRegistryService().execute(
        "final_answer",
        {"answer": "Done"},
    )

    assert set(result.model_dump()) == {
        "tool",
        "output",
        "completion_intent",
    }
    assert result.completion_intent is True


def test_git_status_result_shape_is_stable(tmp_path) -> None:
    repository = _init_git_repository(tmp_path / "repo")

    result = AgentToolRegistryService(workspace_root=repository).execute(
        "git_status",
    )

    assert set(result.model_dump()) == {
        "tool",
        "output",
        "completion_intent",
    }
    assert result.completion_intent is False


def test_write_file_records_workspace_artifact(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)

    result = AgentToolRegistryService(workspace=workspace).execute(
        "write_file",
        {
            "path": "notes.txt",
            "content": "hello world",
        },
    )

    assert result.tool == "write_file"
    artifacts = RuntimeWorkspaceArtifactService(
        workspace
    ).list_workspace_artifacts(workspace.configuration.workspace_id)
    assert len(artifacts) == 1
    assert artifacts[0].tool == "write_file"
    assert artifacts[0].path == "notes.txt"
    assert artifacts[0].metadata == {"bytes_written": 11}
    assert "hello world" not in artifacts[0].summary


def test_git_checkpoint_records_workspace_artifact(tmp_path) -> None:
    repository = _init_git_repository(tmp_path / "repo")
    (repository / "change.txt").write_text("change", encoding="utf-8")
    workspace = RuntimeWorkspaceService(repository)

    result = AgentToolRegistryService(workspace=workspace).execute(
        "git_checkpoint",
        {"message": "Checkpoint"},
    )

    assert result.tool == "git_checkpoint"
    artifacts = RuntimeWorkspaceArtifactService(
        workspace
    ).list_workspace_artifacts(workspace.configuration.workspace_id)
    assert len(artifacts) == 1
    assert artifacts[0].tool == "git_checkpoint"
    assert artifacts[0].artifact_type == "git_commit"
    assert artifacts[0].metadata["commit_hash"]


def test_read_and_list_tools_do_not_record_artifacts(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("Notes", encoding="utf-8")
    runtime_workspace = RuntimeWorkspaceService(workspace)

    registry = AgentToolRegistryService(workspace=runtime_workspace)
    registry.execute("read_file", {"path": "notes.txt"})
    registry.execute("list_directory", {"path": "."})

    artifacts = RuntimeWorkspaceArtifactService(
        runtime_workspace
    ).list_workspace_artifacts(runtime_workspace.configuration.workspace_id)
    assert artifacts == []


@pytest.mark.parametrize(
    ("tool", "arguments", "argument"),
    [
        ("observe", {}, "message"),
        ("final_answer", {}, "answer"),
        ("observe", {"message": 1}, "message"),
        ("final_answer", {"answer": False}, "answer"),
        (
            "propose_change",
            {"description": "Detailed change"},
            "title",
        ),
        (
            "propose_change",
            {"title": "Change title"},
            "description",
        ),
        ("read_file", {}, "path"),
        ("list_directory", {}, "path"),
        ("write_file", {"content": "value"}, "path"),
        ("write_file", {"path": "output.txt"}, "content"),
        ("run_shell", {}, "command"),
        ("run_shell", {"command": ""}, "command"),
        ("git_checkpoint", {}, "message"),
        ("git_checkpoint", {"message": ""}, "message"),
        ("git_create_branch", {}, "branch"),
    ],
)
def test_required_string_arguments_are_enforced(
    tool: str,
    arguments: dict,
    argument: str,
) -> None:
    with pytest.raises(ValueError, match=rf"argument '{argument}'"):
        AgentToolRegistryService().execute(tool, arguments)


def test_unexpected_arguments_are_rejected_deterministically() -> None:
    with pytest.raises(
        ValueError,
        match=r"unexpected argument\(s\): alpha, zeta",
    ):
        AgentToolRegistryService().execute(
            "observe",
            {
                "message": "Valid observation",
                "zeta": True,
                "alpha": True,
            },
        )


def test_read_file_returns_utf8_contents(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("Stratum notes\n", encoding="utf-8")

    result = AgentToolRegistryService(workspace_root=workspace).execute(
        "read_file",
        {"path": "notes.txt"},
    )

    assert result.output == "Stratum notes\n"


def test_read_file_rejects_path_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the workspace"):
        AgentToolRegistryService(workspace_root=workspace).execute(
            "read_file",
            {"path": "../outside.txt"},
        )


def test_read_file_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ValueError, match="File does not exist"):
        AgentToolRegistryService(workspace_root=tmp_path).execute(
            "read_file",
            {"path": "missing.txt"},
        )


def test_git_tools_reject_non_git_workspace_cleanly(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="not a git repository"):
        AgentToolRegistryService(workspace_root=workspace).execute(
            "git_status",
        )
    with pytest.raises(ValueError, match="not a git repository"):
        AgentToolRegistryService(workspace_root=workspace).execute(
            "git_create_branch",
            {"branch": "feature/test"},
        )


def test_list_directory_returns_sorted_names(tmp_path) -> None:
    directory = tmp_path / "entries"
    directory.mkdir()
    for name in ["zeta.txt", "alpha.txt", "middle"]:
        (directory / name).touch()

    result = AgentToolRegistryService(workspace_root=tmp_path).execute(
        "list_directory",
        {"path": "entries"},
    )

    assert json.loads(result.output) == [
        "alpha.txt",
        "middle",
        "zeta.txt",
    ]


def test_list_directory_rejects_path_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "outside").mkdir()

    with pytest.raises(ValueError, match="outside the workspace"):
        AgentToolRegistryService(workspace_root=workspace).execute(
            "list_directory",
            {"path": "../outside"},
        )


def test_write_file_creates_parent_and_returns_summary(tmp_path) -> None:
    result = AgentToolRegistryService(workspace_root=tmp_path).execute(
        "write_file",
        {
            "path": "nested/output.txt",
            "content": "Written safely.",
        },
    )

    assert (tmp_path / "nested" / "output.txt").read_text(
        encoding="utf-8"
    ) == "Written safely."
    assert json.loads(result.output) == {
        "path": "nested/output.txt",
        "bytes_written": 15,
    }


def test_write_file_rejects_path_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="outside the workspace"):
        AgentToolRegistryService(workspace_root=workspace).execute(
            "write_file",
            {
                "path": "../outside.txt",
                "content": "Not written.",
            },
        )

    assert not (tmp_path / "outside.txt").exists()


def test_run_shell_captures_process_result(tmp_path) -> None:
    result = AgentToolRegistryService(workspace_root=tmp_path).execute(
        "run_shell",
        {"command": "printf output; printf error >&2; exit 3"},
    )

    assert json.loads(result.output) == {
        "stdout": "output",
        "stderr": "error",
        "exit_code": 3,
    }
    assert result.event_metadata == {
        "stdout": "output",
        "stderr": "error",
        "exit_code": 3,
        "success": False,
    }


def test_run_shell_timeout_is_reported(monkeypatch, tmp_path) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=kwargs.get("args", ["sh"]),
            timeout=1,
            output="partial",
            stderr="warn",
        )

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    result = AgentToolRegistryService(
        workspace_root=tmp_path,
        shell_timeout_seconds=1,
    ).execute("run_shell", {"command": "printf stalled"})

    assert json.loads(result.output) == {
        "stdout": "partial",
        "stderr": "warn\nCommand timed out after 1 seconds",
        "exit_code": 124,
    }
    assert result.event_metadata["success"] is False


def test_run_shell_rejects_unsafe_cwd_before_execution(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="outside the workspace"):
        AgentToolRegistryService(workspace_root=workspace).execute(
            "run_shell",
            {
                "command": "printf executed > marker.txt",
                "cwd": "..",
            },
        )

    assert not (tmp_path / "marker.txt").exists()


def test_git_status_returns_branch_and_porcelain_status(tmp_path) -> None:
    repository = _init_git_repository(tmp_path / "repo")
    (repository / "tracked.txt").write_text("changed", encoding="utf-8")
    (repository / "untracked.txt").write_text("new", encoding="utf-8")

    result = AgentToolRegistryService(
        workspace_root=repository
    ).execute("git_status")
    output = json.loads(result.output)

    assert output["branch"] == _git(
        repository,
        "branch",
        "--show-current",
    ).stdout.strip()
    assert output["status"].splitlines() == [
        " M tracked.txt",
        "?? untracked.txt",
    ]


def test_git_create_branch_rejects_unsafe_name(tmp_path) -> None:
    repository = _init_git_repository(tmp_path / "repo")

    with pytest.raises(ValueError, match="Unsafe git branch name"):
        AgentToolRegistryService(
            workspace_root=repository
        ).execute(
            "git_create_branch",
            {"branch": "../unsafe"},
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
