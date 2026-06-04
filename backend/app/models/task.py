from enum import StrEnum

from pydantic import BaseModel


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreate(BaseModel):
    title: str


class Task(BaseModel):
    id: str
    status: TaskStatus
    title: str
    created_at: str
    completed_at: str | None = None
    summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
