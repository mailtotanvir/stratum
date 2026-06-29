from fastapi import APIRouter, HTTPException

from app.models.agent_execution import (
    AgentExecutionRecord,
    AgentExecutionRequest,
)
from app.services.agent_execution_service import AgentExecutionService
from app.services.event_service import event_service
from app.services.provider_execution_service import ProviderExecutionService
from app.services.runtime_session_service import (
    RuntimeSessionNotFoundError,
    runtime_session_service,
)


router = APIRouter()
agent_execution_service = AgentExecutionService(
    provider_execution=ProviderExecutionService(events=event_service),
    events=event_service,
)


@router.post("/runtime/agent-execution")
def execute_agent(
    request: AgentExecutionRequest,
) -> AgentExecutionRecord:
    return agent_execution_service.execute(request)


@router.post("/runtime/sessions/{runtime_session_id}/agent-execution")
def execute_agent_for_runtime_session(
    runtime_session_id: str,
    request: AgentExecutionRequest,
) -> AgentExecutionRecord:
    try:
        runtime_session_service.get_session(runtime_session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    normalized_request = request.model_copy(
        update={"runtime_session_id": runtime_session_id},
        deep=True,
    )
    return agent_execution_service.execute(normalized_request)
