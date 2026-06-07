from pydantic import BaseModel, Field

from app.models.proposal import ProposalSourceType


class DecisionTrail(BaseModel):
    proposal_id: str
    recommendation_id: str | None = None
    decision_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_type: ProposalSourceType
    created_at: str | None = None
