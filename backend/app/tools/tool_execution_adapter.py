from typing import Protocol

from pydantic import BaseModel, Field


class ToolExecutionResult(BaseModel):
    success: bool
    output_payload: dict | None = None
    error_message: str | None = None
    artifacts: list[dict] = Field(default_factory=list)


class ToolExecutionAdapter(Protocol):
    async def execute(
        self,
        invocation_id: str,
        tool_name: str,
        input_payload: dict | None,
    ) -> ToolExecutionResult:
        """Execute a registered tool for a persisted invocation."""


class MockToolExecutionAdapter:
    def __init__(self, result: ToolExecutionResult | None = None) -> None:
        self._result = result

    async def execute(
        self,
        invocation_id: str,
        tool_name: str,
        input_payload: dict | None,
    ) -> ToolExecutionResult:
        if self._result is not None:
            return self._result

        return ToolExecutionResult(
            success=True,
            output_payload={
                "mock": True,
                "tool": tool_name,
            },
            error_message=None,
            artifacts=[],
        )
