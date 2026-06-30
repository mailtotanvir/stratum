from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AgentInvocationLifecycleState(StrEnum):
    CREATED = "created"
    ACCEPTED = "accepted"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentInvocationLifecycleEventType(StrEnum):
    CREATED = "created"
    ACCEPTED = "accepted"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXTERNAL_EVENT = "external_event"


class AgentInvocationLifecycleEvent(BaseModel):
    event_type: AgentInvocationLifecycleEventType
    state: AgentInvocationLifecycleState
    message: str = Field(min_length=1)
    timestamp: datetime
    source_event_type: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message", "source_event_type")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentInvocationRecord(BaseModel):
    invocation_id: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    runtime_session_id: str | None = Field(default=None, min_length=1)
    state: AgentInvocationLifecycleState
    created_at: datetime
    updated_at: datetime
    history: list[AgentInvocationLifecycleEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("invocation_id", "adapter_id", "capability_id")
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class AgentInvocationSummary(BaseModel):
    invocation_id: str
    adapter_id: str
    capability_id: str
    runtime_session_id: str | None = None
    state: AgentInvocationLifecycleState
    history_length: int = Field(ge=0)
    last_event_type: AgentInvocationLifecycleEventType | None = None
    last_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentInvocationHistorySummary(BaseModel):
    invocation_id: str
    adapter_id: str
    capability_id: str
    runtime_session_id: str | None = None
    created_at: datetime
    updated_at: datetime
    states: list[AgentInvocationLifecycleState]
    events: list[AgentInvocationLifecycleEvent]
