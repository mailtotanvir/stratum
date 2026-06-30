from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.models.agent_loop import (
    AgentLoopToolCall,
    AgentLoopToolDefinition,
    AgentLoopToolResult,
)
from app.services.runtime_workspace_service import RuntimeWorkspaceService
from app.tools.agent_runtime_tools import (
    DEFAULT_MAX_FILE_SIZE,
    AgentRuntimeTool,
    FinalAnswerTool,
    GitCheckpointTool,
    GitCreateBranchTool,
    GitStatusTool,
    ListDirectoryTool,
    ObserveTool,
    ProposeChangeTool,
    ReadFileTool,
    RunShellTool,
    WriteFileTool,
)


class AgentToolRegistryService:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        workspace: RuntimeWorkspaceService | None = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        shell_timeout_seconds: float = 30,
        tools: Iterable[AgentRuntimeTool] | None = None,
    ) -> None:
        boundary = workspace or RuntimeWorkspaceService(workspace_root)
        built_ins = [
            ObserveTool(),
            FinalAnswerTool(),
            GitCheckpointTool(boundary),
            GitCreateBranchTool(boundary),
            GitStatusTool(boundary),
            ProposeChangeTool(),
            ReadFileTool(boundary, max_file_size),
            ListDirectoryTool(boundary),
            RunShellTool(boundary, shell_timeout_seconds),
            WriteFileTool(boundary),
        ]
        selected_tools = built_ins if tools is None else list(tools)
        self._tools = {tool.name: tool for tool in selected_tools}

    def list_tools(self) -> list[AgentLoopToolDefinition]:
        return [
            self._tools[name].definition
            for name in sorted(self._tools)
        ]

    def get_tool(self, name: str) -> AgentLoopToolDefinition:
        return self._get_runtime_tool(name).definition

    def tool_names(self) -> list[str]:
        return [tool.name for tool in self.list_tools()]

    def execute(
        self,
        tool_call: AgentLoopToolCall | str,
        arguments: dict[str, Any] | None = None,
    ) -> AgentLoopToolResult:
        call = (
            tool_call
            if isinstance(tool_call, AgentLoopToolCall)
            else AgentLoopToolCall(
                tool=tool_call,
                arguments=arguments or {},
            )
        )
        return self._get_runtime_tool(call.tool).execute(call.arguments)

    def validate(self, tool_call: AgentLoopToolCall) -> None:
        self._get_runtime_tool(tool_call.tool).validate(
            tool_call.arguments
        )

    def _get_runtime_tool(self, name: str) -> AgentRuntimeTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"Unknown agent loop tool: {name}") from exc


agent_tool_registry_service = AgentToolRegistryService()
