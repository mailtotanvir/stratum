from enum import StrEnum

from pydantic import BaseModel


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProposalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ProposalCreate(BaseModel):
    title: str
    body: str
    task_id: str | None = None


class ProposalRespond(BaseModel):
    decision: ProposalDecision


class Proposal(BaseModel):
    id: str
    task_id: str | None = None
    title: str
    body: str
    status: ProposalStatus
    created_at: str
    resolved_at: str | None = None
    decision: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")

