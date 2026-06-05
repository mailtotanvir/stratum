from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.schema import RuntimeExecutionRecord
from app.models.runtime_execution import RuntimeExecution
from app.runtime.python_async_runtime import python_async_runtime
from app.services.runtime_execution_service import (
    RuntimeExecutionNotFoundError,
    runtime_execution_service,
)

router = APIRouter()


class RuntimeReasonRequest(BaseModel):
    reason: str


def to_runtime_execution(record: RuntimeExecutionRecord) -> RuntimeExecution:
    return RuntimeExecution(
        task_id=record.task_id,
        state=record.state,
        started_at=(
            record.started_at.isoformat()
            if record.started_at is not None
            else None
        ),
        interrupted_at=(
            record.interrupted_at.isoformat()
            if record.interrupted_at is not None
            else None
        ),
        stopped_at=(
            record.stopped_at.isoformat()
            if record.stopped_at is not None
            else None
        ),
        updated_at=record.updated_at.isoformat(),
    )


@router.get("/runtime/tasks")
def list_runtime_tasks() -> list[RuntimeExecution]:
    return [
        to_runtime_execution(record)
        for record in runtime_execution_service.list()
    ]


@router.get("/runtime/tasks/{task_id}")
def get_runtime_task(task_id: str) -> RuntimeExecution:
    try:
        return to_runtime_execution(runtime_execution_service.get(task_id))
    except RuntimeExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/tasks/{task_id}/run")
async def run_task(task_id: str) -> dict:
    return await python_async_runtime.run_task(task_id)


@router.post("/runtime/tasks/{task_id}/interrupt")
async def interrupt_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.interrupt(task_id, request.reason)


@router.post("/runtime/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.stop(task_id, request.reason)
