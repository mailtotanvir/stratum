from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ArtifactKind(StrEnum):
    FILE = "file"
    PATCH = "patch"
    LOG = "log"
    SUMMARY = "summary"
    REPORT = "report"
    UNKNOWN = "unknown"


class ArtifactCreate(BaseModel):
    path: str
    kind: ArtifactKind = ArtifactKind.UNKNOWN
    task_id: str | None = None
    proposal_id: str | None = None
    metadata: dict[str, Any] | None = Field(default=None)


class Artifact(BaseModel):
    id: str
    task_id: str | None = None
    proposal_id: str | None = None
    path: str
    kind: ArtifactKind
    created_at: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
