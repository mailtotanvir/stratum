from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemorySourceSummary(BaseModel):
    event_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    workspace_artifact_count: int = Field(ge=0)
    session_count: int = Field(ge=0)


class WorkingMemory(BaseModel):
    session_id: str | None = None
    task_id: str | None = None
    latest_event_id: int | None = None
    latest_event_type: str | None = None
    active_skill_ids: list[str] = Field(default_factory=list)
    recent_artifact_ids: list[str] = Field(default_factory=list)
    summary: str


class SessionMemory(BaseModel):
    session_id: str
    task_id: str | None = None
    status: str
    event_count: int = Field(ge=0)
    artifact_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    last_activity_at: datetime | None = None
    summary: str


class RepositoryMemory(BaseModel):
    repository_id: str
    generated_at: datetime
    source_summary: MemorySourceSummary
    session_memories: list[SessionMemory]
    skill_ids: list[str]
    artifact_ids: list[str]
    summary: str


class MemoryDiagnostics(BaseModel):
    status: Literal["healthy", "degraded"]
    source_summary: MemorySourceSummary
    working_memory_count: int = Field(ge=0)
    session_memory_count: int = Field(ge=0)
    repository_memory_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    build_timestamp: datetime

