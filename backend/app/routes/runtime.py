from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.schema import (
    ArtifactRecord,
    RuntimeArtifactLinkRecord,
    RuntimeExecutionRecord,
)
from app.models.artifact import Artifact
from app.models.runtime_artifact import RuntimeArtifactAttachment, RuntimeTaskArtifact
from app.models.runtime_execution import RuntimeExecution
from app.models.runtime_session import RuntimeSession
from app.runtime.python_async_runtime import python_async_runtime
from app.runtime.work_loop import work_loop_service
from app.services.artifact_service import ArtifactNotFoundError, artifact_service
from app.services.runtime_artifact_service import (
    RuntimeArtifactAlreadyAttachedError,
    RuntimeArtifactSessionMismatchError,
    runtime_artifact_service,
)
from app.services.runtime_execution_service import (
    RuntimeExecutionNotFoundError,
    runtime_execution_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionNotFoundError,
    runtime_session_service,
)
from app.services.tool_execution_service import ToolDisabledError
from app.services.tool_registry_service import ToolNotFoundError

router = APIRouter()


class RuntimeReasonRequest(BaseModel):
    reason: str


class RuntimeWorkRequest(BaseModel):
    tool_name: str
    input_payload: dict | None = None


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


def to_runtime_session(record) -> RuntimeSession:
    return RuntimeSession(
        id=record.id,
        task_id=record.task_id,
        status=record.status,
        created_at=record.created_at.isoformat(),
        completed_at=(
            record.completed_at.isoformat()
            if record.completed_at is not None
            else None
        ),
    )


def to_artifact(record: ArtifactRecord) -> Artifact:
    return Artifact(
        id=record.id,
        task_id=record.task_id,
        proposal_id=record.proposal_id,
        path=record.path,
        kind=record.kind,
        created_at=record.created_at.isoformat(),
        metadata=artifact_service.metadata_for(record),
    )


def to_runtime_task_artifact(
    record: RuntimeArtifactLinkRecord,
) -> RuntimeTaskArtifact:
    return RuntimeTaskArtifact(
        task_id=record.task_id,
        session_id=record.session_id,
        artifact_id=record.artifact_id,
        attached_at=record.created_at.isoformat(),
        artifact=to_artifact(artifact_service.get_artifact(record.artifact_id)),
    )


@router.get("/runtime/sessions")
def list_runtime_sessions(task_id: str | None = None) -> list[RuntimeSession]:
    return [
        to_runtime_session(record)
        for record in runtime_session_service.list_sessions(task_id=task_id)
    ]


@router.get("/runtime/sessions/{session_id}")
def get_runtime_session(session_id: str) -> RuntimeSession:
    try:
        return to_runtime_session(runtime_session_service.get_session(session_id))
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/sessions/{session_id}/work")
async def run_runtime_work(
    session_id: str,
    request: RuntimeWorkRequest,
) -> dict:
    try:
        return await work_loop_service.run_single_step(
            session_id=session_id,
            tool_name=request.tool_name,
            input_payload=request.input_payload,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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


@router.post("/runtime/tasks/{task_id}/artifacts/{artifact_id}")
def attach_runtime_artifact(
    task_id: str,
    artifact_id: str,
    session_id: str | None = None,
) -> RuntimeArtifactAttachment:
    try:
        runtime_artifact_service.attach_artifact(
            task_id=task_id,
            artifact_id=artifact_id,
            session_id=session_id,
        )
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeArtifactAlreadyAttachedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeArtifactSessionMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return RuntimeArtifactAttachment(
        task_id=task_id,
        artifact_id=artifact_id,
        session_id=session_id,
        attached=True,
    )


@router.get("/runtime/tasks/{task_id}/artifacts")
def list_runtime_task_artifacts(
    task_id: str,
    session_id: str | None = None,
) -> list[RuntimeTaskArtifact]:
    return [
        to_runtime_task_artifact(record)
        for record in runtime_artifact_service.list_task_artifacts(
            task_id,
            session_id=session_id,
        )
    ]


@router.post("/runtime/tasks/{task_id}/interrupt")
async def interrupt_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.interrupt(task_id, request.reason)


@router.post("/runtime/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.stop(task_id, request.reason)
