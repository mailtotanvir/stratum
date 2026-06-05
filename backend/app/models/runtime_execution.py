from enum import StrEnum

from pydantic import BaseModel


class RuntimeExecutionState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"


class RuntimeExecution(BaseModel):
    task_id: str
    state: RuntimeExecutionState
    started_at: str | None = None
    interrupted_at: str | None = None
    stopped_at: str | None = None
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
