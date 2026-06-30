from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class RuntimeSessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"


class RuntimeSession(BaseModel):
    id: str
    task_id: str
    status: RuntimeSessionStatus
    created_at: datetime
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
