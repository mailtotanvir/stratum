from enum import StrEnum

from pydantic import BaseModel


class ReflectionRequestStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"


class ReflectionRequest(BaseModel):
    id: str
    task_id: str
    status: ReflectionRequestStatus
    reasons: list[str]
    created_at: str
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
