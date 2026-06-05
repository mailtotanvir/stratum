from fastapi import APIRouter, HTTPException

from app.db.schema import ToolInvocationRecord
from app.models.tool_invocation import ToolInvocation, ToolInvocationCreate
from app.services.runtime_session_service import RuntimeSessionNotFoundError
from app.services.tool_execution_service import (
    ToolDisabledError,
    tool_execution_service,
)
from app.services.tool_invocation_service import (
    ToolInvocationNotFoundError,
    tool_invocation_service,
)
from app.services.tool_registry_service import ToolNotFoundError

router = APIRouter()


def to_tool_invocation(record: ToolInvocationRecord) -> ToolInvocation:
    return ToolInvocation(
        id=record.id,
        session_id=record.session_id,
        tool_id=record.tool_id,
        status=record.status,
        input_payload=tool_invocation_service.input_payload_for(record),
        output_payload=tool_invocation_service.output_payload_for(record),
        created_at=record.created_at.isoformat(),
        completed_at=(
            record.completed_at.isoformat()
            if record.completed_at is not None
            else None
        ),
    )


@router.post("/runtime/sessions/{session_id}/tools/{tool_id}")
def create_tool_invocation(
    session_id: str,
    tool_id: str,
    request: ToolInvocationCreate | None = None,
) -> ToolInvocation:
    try:
        invocation = tool_invocation_service.create_invocation(
            session_id=session_id,
            tool_id=tool_id,
            input_payload=(
                request.input_payload
                if request is not None
                else None
            ),
        )
        return to_tool_invocation(
            tool_invocation_service.mark_running(invocation.id)
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tool-invocations")
def list_tool_invocations(
    session_id: str | None = None,
    tool_id: str | None = None,
) -> list[ToolInvocation]:
    return [
        to_tool_invocation(record)
        for record in tool_invocation_service.list_invocations(
            session_id=session_id,
            tool_id=tool_id,
        )
    ]


@router.get("/tool-invocations/{invocation_id}")
def get_tool_invocation(invocation_id: str) -> ToolInvocation:
    try:
        return to_tool_invocation(
            tool_invocation_service.get_invocation(invocation_id)
        )
    except ToolInvocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tool-invocations/{invocation_id}/execute")
async def execute_tool_invocation(invocation_id: str) -> ToolInvocation:
    try:
        return to_tool_invocation(
            await tool_execution_service.execute_invocation(invocation_id)
        )
    except ToolInvocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
