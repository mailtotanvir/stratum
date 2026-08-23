"""Tool execution boundary.

Tools are explicit, schema-driven operations against the target workspace.
The AI proposes; the runtime validates; the approval policy decides; the
executor performs. Tool code never talks to providers and never emits
events itself — the engine wraps every invocation in tool.started /
tool.completed / tool.failed events.
"""

from __future__ import annotations

import hashlib
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ToolError


# ---------------------------------------------------------------------------
# Workspace boundary enforcement (safety)
# ---------------------------------------------------------------------------


def resolve_in_workspace(workspace: Path, relative: str | Path) -> Path:
    """Resolve a path strictly inside the workspace. No escapes, ever."""
    candidate = (workspace / relative).resolve()
    if not candidate.is_relative_to(workspace.resolve()):
        raise ToolError(f"path escapes workspace boundary: {relative}")
    return candidate


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ExecutionContext:
    """Everything a tool is allowed to touch."""

    workspace: Path
    # Shared scratch state across steps of one execution (e.g. last-read
    # file contents used to materialize writes).
    scratch: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


class Tool:
    name: str = "tool"
    description: str = ""
    risk_level: str = "medium"
    input_schema: dict[str, Any] = {}

    async def execute(self, params: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from the repository."
    risk_level = "low"
    input_schema = {"path": "string (required): repo-relative file path"}
    max_bytes = 20_000

    async def execute(self, params: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        started = time.monotonic()
        rel = params.get("path")
        if not rel or not isinstance(rel, str):
            raise ToolError("read_file requires 'path'")
        path = resolve_in_workspace(ctx.workspace, rel)
        if not path.is_file():
            raise ToolError(f"file not found: {rel}")
        content = path.read_bytes()[: self.max_bytes].decode("utf-8", errors="replace")
        truncated = path.stat().st_size > self.max_bytes

        # Remember reads so write materialization can be grounded in reality.
        ctx.scratch[f"file:{rel}"] = content

        return ToolResult(
            ok=True,
            summary=f"read {rel} ({path.stat().st_size} bytes)",
            details={
                "path": rel,
                "bytes": path.stat().st_size,
                "truncated": truncated,
                "sha256": file_sha256(path),
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

_WRITE_MAX_BYTES = 200_000


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Write full content to a file inside the repository "
        "(creates parent directories; refuses paths outside the workspace)."
    )
    risk_level = "high"
    input_schema = {
        "path": "string (required): repo-relative target path",
        "content": "string (required): complete new file content",
    }

    async def execute(self, params: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        started = time.monotonic()
        rel = params.get("path")
        content = params.get("content")
        if not rel or not isinstance(rel, str):
            raise ToolError("write_file requires 'path'")
        if not isinstance(content, str):
            raise ToolError("write_file requires string 'content'")
        if len(content.encode("utf-8")) > _WRITE_MAX_BYTES:
            raise ToolError(
                f"write_file content exceeds {_WRITE_MAX_BYTES} bytes; refusing"
            )

        path = resolve_in_workspace(ctx.workspace, rel)
        existed = path.exists()
        before_sha = file_sha256(path) if existed else None
        diff = _unified_diff(path.read_text("utf-8") if existed else "", content)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return ToolResult(
            ok=True,
            summary=f"{'updated' if existed else 'created'} {rel} ({len(content)} chars)",
            details={
                "path": rel,
                "created": not existed,
                "bytes": len(content.encode("utf-8")),
                "before_sha256": before_sha,
                "after_sha256": file_sha256(path),
                "diff": diff[:4000],
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _unified_diff(before: str, after: str) -> str:
    import difflib

    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="before",
        tofile="after",
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------

_RUN_OUTPUT_LIMIT = 10_000
_RUN_TIMEOUT_SECONDS = 120


class RunCommandTool(Tool):
    name = "run_command"
    description = "Run a shell command with the repository as working directory."
    risk_level = "high"
    input_schema = {"command": "string (required): command line to execute"}

    def __init__(self, *, timeout_seconds: float = _RUN_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    async def execute(self, params: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        started = time.monotonic()
        command = params.get("command")
        if not command or not isinstance(command, str):
            raise ToolError("run_command requires 'command'")

        try:
            proc = await _run_subprocess(command, ctx.workspace, self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"command timed out after {self.timeout_seconds}s: {command}"
            ) from exc
        except OSError as exc:
            raise ToolError(f"failed to launch command: {exc}") from exc

        stdout = (proc.stdout or "")[-_RUN_OUTPUT_LIMIT:]
        stderr = (proc.stderr or "")[-_RUN_OUTPUT_LIMIT:]

        return ToolResult(
            ok=proc.returncode == 0,
            summary=f"`{command}` exited {proc.returncode}",
            details={
                "command": command,
                "exit_code": proc.returncode,
                "stdout_tail": stdout,
                "stderr_tail": stderr,
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )


async def _run_subprocess(
    command: str, cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    import asyncio

    argv = shlex.split(command)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise subprocess.TimeoutExpired(cmd=command, timeout=timeout) from None
    return subprocess.CompletedProcess(
        argv, proc.returncode or 0, out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def default_tool_registry() -> dict[str, Tool]:
    tools = [ReadFileTool(), WriteFileTool(), RunCommandTool()]
    return {tool.name: tool for tool in tools}
