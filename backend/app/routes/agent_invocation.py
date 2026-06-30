from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.agent_invocation_lifecycle import (
    AgentInvocationHistorySummary,
    AgentInvocationRecord,
    AgentInvocationSummary,
)
from app.services.agent_invocation_service import agent_invocation_service


router = APIRouter()


class AgentInvocationCreateRequest(BaseModel):
    adapter_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentInvocationCancelRequest(BaseModel):
    message: str = Field(default="Agent invocation cancelled", min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentInvocationListResponse(BaseModel):
    invocations: list[AgentInvocationRecord]


@router.post("/runtime/agent-invocations")
def create_agent_invocation(request: AgentInvocationCreateRequest) -> AgentInvocationRecord:
    try:
        return agent_invocation_service.start_invocation(
            adapter_id=request.adapter_id,
            capability_id=request.capability_id,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runtime/agent-invocations")
def list_agent_invocations(
    limit: int = Query(default=20, ge=1, le=100),
) -> AgentInvocationListResponse:
    return AgentInvocationListResponse(
        invocations=agent_invocation_service.list_recent_invocations(limit=limit)
    )


@router.get("/runtime/agent-invocations/{invocation_id}/status")
def get_agent_invocation_status(invocation_id: str) -> AgentInvocationSummary:
    try:
        return agent_invocation_service.status_summary(invocation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/agent-invocations/{invocation_id}/history")
def get_agent_invocation_history(
    invocation_id: str,
) -> AgentInvocationHistorySummary:
    try:
        return agent_invocation_service.history_summary(invocation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/agent-invocations/{invocation_id}/cancel")
def cancel_agent_invocation(
    invocation_id: str,
    request: AgentInvocationCancelRequest,
) -> AgentInvocationRecord:
    try:
        return agent_invocation_service.cancel_invocation(
            invocation_id,
            message=request.message,
            metadata=request.metadata,
        )
    except ValueError as exc:
        if "is not registered" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
