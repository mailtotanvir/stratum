from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeWorkspaceRepositoryStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    is_git_repository: bool
    branch: str | None = None
    head_commit: str | None = None
    dirty: bool | None = None
    status: str | None = None
    checkpoint_status: str | None = None
    safe_to_run: bool = False
    issues: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeWorkspaceBindingStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace: dict[str, Any]
    repository: RuntimeWorkspaceRepositoryStatus
    workspace_artifact_count: int = 0
    session_artifact_count: int = 0
    linked_session_ids: list[str] = Field(default_factory=list)
    runtime_execution_allowed: bool = False
    runtime_execution_reason: str
    checked_at: datetime

