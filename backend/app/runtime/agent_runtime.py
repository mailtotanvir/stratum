from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentRuntime(Protocol):
    async def run_task(self, task_id: str) -> dict:
        """Start runtime handling for a task."""

    async def interrupt(self, task_id: str, reason: str) -> dict:
        """Request an interrupt for active task handling."""

    async def stop(self, task_id: str, reason: str) -> dict:
        """Request runtime stop for active task handling."""
