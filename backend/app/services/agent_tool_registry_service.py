from collections.abc import Callable
from typing import Any

from app.models.agent_loop import (
    AgentLoopToolCall,
    AgentLoopToolDefinition,
    AgentLoopToolResult,
)


AgentTool = Callable[[dict[str, Any]], AgentLoopToolResult]


class AgentToolRegistryService:
    def __init__(self) -> None:
        self._definitions = {
            "observe": AgentLoopToolDefinition(
                name="observe",
                description="Record an observation and continue the agent loop.",
                argument_schema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                    },
                    "required": ["message"],
                    "additionalProperties": False,
                },
            ),
            "final_answer": AgentLoopToolDefinition(
                name="final_answer",
                description="Return the final answer and complete the agent loop.",
                argument_schema={
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                    },
                    "required": ["answer"],
                    "additionalProperties": False,
                },
                completion_tool=True,
            ),
        }
        self._tools: dict[str, AgentTool] = {
            "observe": self._observe,
            "final_answer": self._final_answer,
        }

    def list_tools(self) -> list[AgentLoopToolDefinition]:
        return [
            self._definitions[name]
            for name in sorted(self._definitions)
        ]

    def get_tool(self, name: str) -> AgentLoopToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise ValueError(f"Unknown agent loop tool: {name}") from exc

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
        try:
            tool = self._tools[call.tool]
        except KeyError as exc:
            raise ValueError(f"Unknown agent loop tool: {call.tool}") from exc
        return tool(call.arguments)

    @staticmethod
    def _observe(arguments: dict[str, Any]) -> AgentLoopToolResult:
        _reject_unexpected_arguments(arguments, {"message"}, "observe")
        message = _required_string(arguments, "message", "observe")
        return AgentLoopToolResult(
            tool="observe",
            output=message,
        )

    @staticmethod
    def _final_answer(arguments: dict[str, Any]) -> AgentLoopToolResult:
        _reject_unexpected_arguments(
            arguments,
            {"answer"},
            "final_answer",
        )
        answer = _required_string(arguments, "answer", "final_answer")
        return AgentLoopToolResult(
            tool="final_answer",
            output=answer,
            completion_intent=True,
        )


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


agent_tool_registry_service = AgentToolRegistryService()


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
