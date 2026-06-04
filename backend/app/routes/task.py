from fastapi import APIRouter, HTTPException

from app.db.schema import TaskRecord
from app.models.task import Task, TaskCreate
from app.services.event_service import event_service
from app.services.task_service import TaskNotFoundError, task_service

router = APIRouter()


def to_task(record: TaskRecord) -> Task:
    return Task(
        id=record.id,
        title=record.title,
        status=record.status,
        created_at=record.created_at.isoformat(),
        completed_at=(
            record.completed_at.isoformat()
            if record.completed_at is not None
            else None
        ),
        summary=record.summary,
    )


@router.post("/tasks")
def create_task(request: TaskCreate) -> Task:
    return to_task(task_service.create_task(request.title))


@router.get("/tasks/{task_id}/trace")
def task_trace(
    task_id: str,
    type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    return [
        event.to_dict()
        for event in event_service.list_persisted_events(
            event_type=type,
            task_id=task_id,
            limit=limit,
        )
    ]


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> Task:
    try:
        return to_task(task_service.get_task(task_id))
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks")
def list_tasks() -> list[Task]:
    return [to_task(task) for task in task_service.list_tasks()]
