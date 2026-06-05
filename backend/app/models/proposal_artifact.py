from pydantic import BaseModel

from app.models.artifact import Artifact


class ProposalArtifactAttachment(BaseModel):
    proposal_id: str
    artifact_id: str
    attached: bool

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class ProposalArtifact(BaseModel):
    proposal_id: str
    artifact_id: str
    attached_at: str
    artifact: Artifact

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
