from enum import StrEnum

from pydantic import BaseModel


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    description: str


class Task(BaseModel):
    id: str
    created_at: str
    updated_at: str
    status: TaskStatus
    description: str

    def to_dict(self) -> dict[str, str]:
        return self.model_dump(mode="json")

