from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(StrEnum):
    ASK_HUMAN_REQUESTED = "ask_human_requested"
    ASK_HUMAN_RESPONDED = "ask_human_responded"
    DEMO_TASK_COMPLETED = "demo_task_completed"
    RUNTIME_TASK_STARTED = "runtime_task_started"
    RUNTIME_TASK_INTERRUPTED = "runtime_task_interrupted"
    RUNTIME_TASK_STOPPED = "runtime_task_stopped"
    RUNTIME_GOVERNANCE_WARNING = "runtime_governance_warning"
    RUNTIME_GOVERNANCE_BLOCKED = "runtime_governance_blocked"
    REFLECTION_REQUESTED = "reflection_requested"
    REFLECTION_RESOLVED = "reflection_resolved"
    INTERRUPT_REQUESTED = "interrupt_requested"
    INTERRUPT_APPLIED = "interrupt_applied"
    INTERRUPT_IGNORED = "interrupt_ignored"
    STOP_REQUESTED = "stop_requested"
    STOP_APPLIED = "stop_applied"
    STOP_IGNORED = "stop_ignored"
    TASK_CREATED = "task_created"
    TASK_RUNNING = "task_running"
    TASK_FAILED = "task_failed"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    PROPOSAL_GENERATED = "proposal_generated"
    PROPOSAL_RESOLVED = "proposal_resolved"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    WARNING = "warning"
    ERROR = "error"


class RuntimeEvent(BaseModel):
    id: int
    ts: str
    type: EventType
    severity: Severity = Severity.INFO
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity", mode="before")
    @classmethod
    def default_severity(cls, value: Any) -> Any:
        return Severity.INFO if value is None else value

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
