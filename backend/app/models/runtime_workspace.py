from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeWorkspace(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str
    name: str
    root_path: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class RuntimeWorkspaceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str
    name: str
    root_path: str
    active: bool
