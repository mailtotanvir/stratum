from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(StrEnum):
    ASK_HUMAN_REQUESTED = "ask_human_requested"
    ASK_HUMAN_RESPONDED = "ask_human_responded"
    DEMO_TASK_COMPLETED = "demo_task_completed"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    WARNING = "warning"
    ERROR = "error"


class RuntimeEvent(BaseModel):
    id: int
    ts: str
    type: EventType
    severity: Severity
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

