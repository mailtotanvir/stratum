from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.artifact import Artifact
from app.models.proposal import Proposal
from app.models.task import Task
from app.models.repository_intelligence import RepositoryIntelligenceSummary
from app.models.transformation_history import RepositoryChangeSummary, TransformationHistoryProjection


class TransformationAttachmentRequest(BaseModel):
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)
    kind: str = Field(min_length=1, default="summary")
    path: str | None = None


class TransformationSessionCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    specification: str = Field(min_length=1)
    context_markdown: str | None = None
    requested_by: str = "operator"
    validation_command: str | None = None
    affected_files: list[str] = Field(default_factory=list)


class TransformationSessionArtifact(BaseModel):
    artifact_id: str
    path: str
    kind: str
    label: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransformationSessionPatchProposal(BaseModel):
    patch_id: str
    status: str
    validation_command: str | None = None
    rollback_reference: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    proposal_id: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransformationSessionSummary(BaseModel):
    transformation_id: str
    task: Task
    proposal: Proposal
    repository_summary: RepositoryChangeSummary
    repository_intelligence: RepositoryIntelligenceSummary
    artifacts: list[TransformationSessionArtifact]
    patch: TransformationSessionPatchProposal
    history: TransformationHistoryProjection
    summary: str
    created_at: datetime
    updated_at: datetime
    validation_command: str | None = None
    checkpoint_commit: str | None = None
    rollback_reference: str | None = None
    approvals_required: bool = True


class TransformationSessionCollection(BaseModel):
    items: list[TransformationSessionSummary]
    total: int

