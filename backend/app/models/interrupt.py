from enum import StrEnum

from pydantic import BaseModel


class InterruptRequestStatus(StrEnum):
    REQUESTED = "requested"
    APPLIED = "applied"
    IGNORED = "ignored"


class InterruptRequest(BaseModel):
    id: str
    task_id: str
    reason: str
    status: InterruptRequestStatus
    created_at: str
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
