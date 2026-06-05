from pydantic import BaseModel

from app.models.artifact import Artifact


class RuntimeArtifactAttachment(BaseModel):
    task_id: str
    artifact_id: str
    session_id: str | None = None
    attached: bool

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class RuntimeTaskArtifact(BaseModel):
    task_id: str
    session_id: str | None = None
    artifact_id: str
    attached_at: str
    artifact: Artifact

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
