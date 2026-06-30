from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ArtifactStatus = Literal["proposed", "created", "attached", "generated", "validated", "failed", "reverted"]
PatchStatus = Literal["proposed", "approved", "rejected", "applied", "failed", "reverted"]
ChangeStatus = Literal["clean", "dirty", "unsafe", "unknown"]


class ArtifactRecordView(BaseModel):
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    path: str = Field(min_length=1)
    origin_event_id: int | None = None
    session_id: str | None = None
    workspace_id: str | None = None
    producer: str | None = None
    status: ArtifactStatus
    metadata: dict[str, object] = Field(default_factory=dict)
    checksum: str | None = None


class PatchRecordView(BaseModel):
    id: str = Field(min_length=1)
    session_id: str | None = None
    proposal_id: str | None = None
    artifact_id: str | None = None
    status: PatchStatus
    affected_files: list[str] = Field(default_factory=list)
    origin_event_id: int | None = None
    approval_event_id: int | None = None
    validation_result: str | None = None
    rollback_reference: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class RepositoryChangeSummary(BaseModel):
    workspace_id: str | None = None
    path: str | None = None
    repository_detected: bool
    branch: str | None = None
    head_commit: str | None = None
    dirty_workspace: bool = False
    unsafe_workspace: bool = False
    modified_files: list[str] = Field(default_factory=list)
    added_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    diff_summaries: list[str] = Field(default_factory=list)
    git_status: list[str] = Field(default_factory=list)
    checkpoint_commit: str | None = None
    rollback_reference: str | None = None
    warnings: list[str] = Field(default_factory=list)
    status: ChangeStatus = "unknown"
    metadata: dict[str, object] = Field(default_factory=dict)


class TransformationHistoryItem(BaseModel):
    timestamp: datetime
    session_id: str | None = None
    task_id: str | None = None
    proposal_id: str | None = None
    patch_id: str | None = None
    artifact_id: str | None = None
    event_id: int | None = None
    stage: str = Field(min_length=1)
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class TransformationHistorySummary(BaseModel):
    total_events: int = Field(ge=0)
    repeated_patterns: list[str] = Field(default_factory=list)
    failed_attempts: int = Field(ge=0)
    sessions_with_transformations: int = Field(ge=0)


class TransformationHistoryProjection(BaseModel):
    items: list[TransformationHistoryItem]
    summary: TransformationHistorySummary

