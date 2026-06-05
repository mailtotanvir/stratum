from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolInvocationStatus(StrEnum):
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolInvocationCreate(BaseModel):
    input_payload: dict[str, Any] | None = Field(default=None)


class ToolInvocation(BaseModel):
    id: str
    session_id: str
    tool_id: str
    status: ToolInvocationStatus
    input_payload: dict[str, Any] | None = None
    output_payload: dict[str, Any] | None = None
    created_at: str
    completed_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
