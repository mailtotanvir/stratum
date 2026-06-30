from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ArtifactKind(StrEnum):
    FILE = "file"
    PATCH = "patch"
    LOG = "log"
    SUMMARY = "summary"
    REPORT = "report"
    PLAN = "plan"
    COMMAND_OUTPUT = "command_output"
    EVALUATION_EVIDENCE = "evaluation_evidence"
    EXTERNAL_AGENT_OUTPUT = "external_agent_output"
    RUNTIME_LOG = "runtime_log"
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
    origin_event_id: int | None = None
    session_id: str | None = None
    workspace_id: str | None = None
    producer: str | None = None
    status: str = "created"
    metadata: dict[str, Any] | None = None
    checksum: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
