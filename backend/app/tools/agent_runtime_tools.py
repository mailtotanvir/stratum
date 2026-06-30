import json
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.models.agent_loop import (
    AgentLoopToolDefinition,
    AgentLoopToolResult,
)
from app.services.runtime_workspace_service import RuntimeWorkspaceService


DEFAULT_MAX_FILE_SIZE = 64 * 1024


class AgentRuntimeTool(ABC):
    name: str
    description: str
    argument_schema: dict[str, Any]
    requires_approval: bool = False
    completion_tool: bool = False

    @property
    def definition(self) -> AgentLoopToolDefinition:
        return AgentLoopToolDefinition(
            name=self.name,
            description=self.description,
            argument_schema=self.argument_schema,
            requires_approval=self.requires_approval,
            completion_tool=self.completion_tool,
        )

    def validate(self, arguments: dict[str, Any]) -> None:
        expected = set(self.argument_schema["properties"])
        _reject_unexpected_arguments(arguments, expected, self.name)
        for name in self.argument_schema.get("required", []):
            _required_string(arguments, name, self.name)

    @abstractmethod
    def execute(
        self,
        arguments: dict[str, Any],
    ) -> AgentLoopToolResult:
        raise NotImplementedError


class ObserveTool(AgentRuntimeTool):
    name = "observe"
    description = "Record an observation and continue the agent loop."
    requires_approval = False
    argument_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        return AgentLoopToolResult(
            tool=self.name,
            output=_required_string(arguments, "message", self.name),
        )


class FinalAnswerTool(AgentRuntimeTool):
    name = "final_answer"
    description = "Return the final answer and complete the agent loop."
    requires_approval = False
    completion_tool = True
    argument_schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        return AgentLoopToolResult(
            tool=self.name,
            output=_required_string(arguments, "answer", self.name),
            completion_intent=True,
        )


class ProposeChangeTool(AgentRuntimeTool):
    name = "propose_change"
    description = "Propose a change without executing it."
    requires_approval = True
    argument_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["title", "description"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        title = _required_string(arguments, "title", self.name)
        description = _required_string(
            arguments,
            "description",
            self.name,
        )
        return AgentLoopToolResult(
            tool=self.name,
            output=f"{title}: {description}",
        )


class ReadFileTool(AgentRuntimeTool):
    name = "read_file"
    description = "Read a UTF-8 text file within the workspace."
    requires_approval = False
    argument_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        workspace: RuntimeWorkspaceService,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        if max_file_size <= 0:
            raise ValueError("max_file_size must be positive")
        self._workspace = workspace
        self._max_file_size = max_file_size

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        path = self._workspace.validate_relative_path(
            _required_string(arguments, "path", self.name)
        )
        if not path.exists():
            raise ValueError(f"File does not exist: {path.name}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path.name}")
        if path.stat().st_size > self._max_file_size:
            raise ValueError(
                f"File exceeds maximum size of {self._max_file_size} bytes"
            )
        try:
            output = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("File is not valid UTF-8 text") from exc
        return AgentLoopToolResult(tool=self.name, output=output)


class ListDirectoryTool(AgentRuntimeTool):
    name = "list_directory"
    description = "List names in a directory within the workspace."
    requires_approval = False
    argument_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: RuntimeWorkspaceService) -> None:
        self._workspace = workspace

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        path = self._workspace.validate_relative_path(
            _required_string(arguments, "path", self.name)
        )
        if not path.exists():
            raise ValueError(f"Directory does not exist: {path.name}")
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path.name}")
        names = sorted(entry.name for entry in path.iterdir())
        return AgentLoopToolResult(
            tool=self.name,
            output=json.dumps(names),
        )


class WriteFileTool(AgentRuntimeTool):
    name = "write_file"
    description = "Write UTF-8 text to a file within the workspace."
    requires_approval = True
    argument_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: RuntimeWorkspaceService) -> None:
        self._workspace = workspace

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        path = self._workspace.validate_relative_path(
            _required_string(arguments, "path", self.name)
        )
        content = _required_string(arguments, "content", self.name)
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Content is not valid UTF-8 text") from exc
        if path.exists() and not path.is_file():
            raise ValueError(f"Path is not a file: {path.name}")

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        relative_path = self._workspace.relative_path(path)
        self._workspace.record_artifact(
            tool=self.name,
            path=relative_path,
            artifact_type="file_write",
            summary=f"Wrote {relative_path}",
            metadata={
                "bytes_written": len(encoded),
            },
        )
        return AgentLoopToolResult(
            tool=self.name,
            output=json.dumps(
                {
                    "path": relative_path,
                    "bytes_written": len(encoded),
                },
                sort_keys=True,
            ),
        )


class RunShellTool(AgentRuntimeTool):
    name = "run_shell"
    description = "Run a shell command within the workspace."
    requires_approval = True
    argument_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        workspace: RuntimeWorkspaceService,
        timeout_seconds: float = 30,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._workspace = workspace
        self._timeout_seconds = timeout_seconds

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        if "cwd" in arguments:
            _required_string(arguments, "cwd", self.name)

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        command = _required_string(arguments, "command", self.name)
        cwd = self._workspace.validate_relative_path(
            arguments.get("cwd", ".")
        )
        if not cwd.exists():
            raise ValueError(f"Directory does not exist: {cwd.name}")
        if not cwd.is_dir():
            raise ValueError(f"Path is not a directory: {cwd.name}")

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = _timeout_output(exc.stdout)
            stderr = _timeout_output(exc.stderr)
            if stderr:
                stderr += "\n"
            stderr += (
                f"Command timed out after {self._timeout_seconds:g} seconds"
            )
            exit_code = 124

        details = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }
        meaningful = exit_code != 0 or bool(stdout.strip()) or bool(stderr.strip())
        if meaningful:
            self._workspace.record_artifact(
                tool=self.name,
                artifact_type="shell_output",
                summary=(
                    "Shell command produced output"
                    if exit_code == 0
                    else "Shell command failed"
                ),
                metadata={
                    "exit_code": exit_code,
                    "stdout_bytes": len(stdout.encode("utf-8", errors="replace")),
                    "stderr_bytes": len(stderr.encode("utf-8", errors="replace")),
                },
            )
        return AgentLoopToolResult(
            tool=self.name,
            output=json.dumps(details, sort_keys=True),
            event_metadata={
                **details,
                "success": exit_code == 0,
            },
        )


class GitStatusTool(AgentRuntimeTool):
    name = "git_status"
    description = "Show the current branch and porcelain git status."
    requires_approval = False
    argument_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    }

    def __init__(self, workspace: RuntimeWorkspaceService) -> None:
        self._workspace = workspace

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        if "path" in arguments:
            _required_string(arguments, "path", self.name)

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        repository = _git_repository(
            self._workspace,
            arguments.get("path", "."),
        )
        branch = _run_git(
            ["branch", "--show-current"],
            repository,
        ).stdout.strip() or "HEAD"
        status = _run_git(
            ["status", "--porcelain", "--", ".", ":(exclude).stratum"],
            repository,
        ).stdout.rstrip()
        details = {"branch": branch, "status": status}
        return AgentLoopToolResult(
            tool=self.name,
            output=json.dumps(details, sort_keys=True),
            event_metadata={**details, "success": True},
        )


class GitCheckpointTool(AgentRuntimeTool):
    name = "git_checkpoint"
    description = "Commit all current workspace repository changes."
    requires_approval = True
    argument_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: RuntimeWorkspaceService) -> None:
        self._workspace = workspace

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        message = _required_string(arguments, "message", self.name)
        repository = _git_repository(
            self._workspace,
            ".",
        )
        if not _run_git(
            ["status", "--porcelain"],
            repository,
        ).stdout.strip():
            raise ValueError("Git checkpoint requires workspace changes")
        _run_git(["add", "-A"], repository)
        committed = _run_git(
            [
                "-c",
                "commit.gpgSign=false",
                "commit",
                "-m",
                message,
            ],
            repository,
        )
        commit_hash = _run_git(
            ["rev-parse", "HEAD"],
            repository,
        ).stdout.strip()
        details = {
            "commit_hash": commit_hash,
            "message": message,
        }
        self._workspace.record_artifact(
            tool=self.name,
            artifact_type="git_commit",
            summary=f"Created git checkpoint {commit_hash}",
            metadata={
                "commit_hash": commit_hash,
            },
        )
        return AgentLoopToolResult(
            tool=self.name,
            output=json.dumps(details, sort_keys=True),
            event_metadata={
                "commit_hash": commit_hash,
                "commit_message": message,
                "stdout": committed.stdout,
                "stderr": committed.stderr,
                "exit_code": committed.returncode,
                "success": True,
            },
        )


class GitCreateBranchTool(AgentRuntimeTool):
    name = "git_create_branch"
    description = "Create and switch to a new local git branch."
    requires_approval = True
    argument_schema = {
        "type": "object",
        "properties": {"branch": {"type": "string"}},
        "required": ["branch"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: RuntimeWorkspaceService) -> None:
        self._workspace = workspace

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        branch = _required_string(arguments, "branch", self.name)
        checked = subprocess.run(
            ["git", "check-ref-format", "--branch", branch],
            cwd=self._workspace.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if checked.returncode != 0:
            raise ValueError(f"Unsafe git branch name: {branch}")

    def execute(self, arguments: dict[str, Any]) -> AgentLoopToolResult:
        self.validate(arguments)
        branch = _required_string(arguments, "branch", self.name)
        repository = _git_repository(
            self._workspace,
            ".",
        )
        switched = _run_git(["switch", "-c", branch], repository)
        details = {"branch": branch}
        return AgentLoopToolResult(
            tool=self.name,
            output=json.dumps(details, sort_keys=True),
            event_metadata={
                **details,
                "stdout": switched.stdout,
                "stderr": switched.stderr,
                "exit_code": switched.returncode,
                "success": True,
            },
        )


def _git_repository(
    workspace: RuntimeWorkspaceService,
    relative_path: str,
) -> Path:
    path = workspace.validate_relative_path(relative_path)
    if not path.exists() or not path.is_dir():
        raise ValueError("Git repository path is not a directory")
    result = _run_git(
        ["rev-parse", "--show-toplevel"],
        path,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("Workspace path is not a git repository")
    repository = Path(result.stdout.strip()).resolve()
    try:
        repository.relative_to(workspace.root)
    except ValueError as exc:
        raise ValueError(
            "Git repository is outside the workspace"
        ) from exc
    return repository


def _run_git(
    arguments: list[str],
    cwd: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"Git command failed: {message}")
    return result
    return result


def _timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _required_string(
    arguments: dict[str, Any],
    name: str,
    tool: str,
) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Agent loop tool '{tool}' requires non-empty string "
            f"argument '{name}'"
        )
    return value


def _reject_unexpected_arguments(
    arguments: dict[str, Any],
    expected: set[str],
    tool: str,
) -> None:
    unexpected = sorted(set(arguments) - expected)
    if unexpected:
        names = ", ".join(unexpected)
        raise ValueError(
            f"Agent loop tool '{tool}' received unexpected "
            f"argument(s): {names}"
        )
