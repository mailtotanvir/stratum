import sys

import pytest

from stratum.errors import ToolError
from stratum.tools import (
    ExecutionContext,
    ReadFileTool,
    RunCommandTool,
    WriteFileTool,
    resolve_in_workspace,
)


@pytest.fixture
def tool_ctx(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')\n")
    return ExecutionContext(workspace=tmp_path)


async def test_read_file(tool_ctx):
    result = await ReadFileTool().execute({"path": "hello.py"}, tool_ctx)
    assert result.ok
    assert "print('hi')" in tool_ctx.scratch["file:hello.py"]
    assert result.details["bytes"] == len("print('hi')\n")


async def test_read_missing_file_raises(tool_ctx):
    with pytest.raises(ToolError, match="not found"):
        await ReadFileTool().execute({"path": "nope.py"}, tool_ctx)


async def test_write_creates_then_updates(tool_ctx):
    tool = WriteFileTool()
    created = await tool.execute(
        {"path": "src/new.py", "content": "x = 1\n"}, tool_ctx)
    assert created.ok and created.details["created"]

    updated = await tool.execute(
        {"path": "src/new.py", "content": "x = 2\n"}, tool_ctx)
    assert not updated.details["created"]
    assert "-x = 1" in updated.details["diff"]
    assert "+x = 2" in updated.details["diff"]
    assert updated.details["before_sha256"] != updated.details["after_sha256"]


async def test_write_rejects_escaping_path(tool_ctx):
    with pytest.raises(ToolError, match="escapes workspace"):
        await WriteFileTool().execute(
            {"path": "../evil.py", "content": "boom"}, tool_ctx)


def test_resolve_rejects_absolute_outside(tmp_path):
    with pytest.raises(ToolError, match="escapes workspace"):
        resolve_in_workspace(tmp_path, "/etc/passwd")


async def test_run_command_success_and_failure(tool_ctx):
    tool = RunCommandTool()
    ok = await tool.execute(
        {"command": f"{sys.executable} -c \"print('ran')\""}, tool_ctx)
    assert ok.ok and "ran" in ok.details["stdout_tail"]

    fail = await tool.execute({"command": "false"}, tool_ctx)
    assert not fail.ok and fail.details["exit_code"] != 0


async def test_run_command_runs_inside_workspace(tool_ctx):
    tool = RunCommandTool()
    result = await tool.execute({"command": "pwd"}, tool_ctx)
    assert str(tool_ctx.workspace) in result.details["stdout_tail"]
