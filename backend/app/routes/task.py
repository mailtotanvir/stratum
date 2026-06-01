from fastapi import APIRouter, HTTPException

from app.models.task import Task, TaskCreate
from app.services.task_service import TaskNotFoundError, task_service

router = APIRouter()


@router.post("/task")
def create_task(request: TaskCreate) -> Task:
    return task_service.create_task(request.description)


@router.get("/task/{task_id}")
def get_task(task_id: str) -> Task:
    try:
        return task_service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks")
def list_tasks() -> list[Task]:
    return task_service.list_tasks()

