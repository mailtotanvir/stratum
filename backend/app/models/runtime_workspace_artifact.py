from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeWorkspaceArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    workspace_id: str
    session_id: str | None = None
    tool: str
    path: str | None = None
    artifact_type: str
    summary: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
