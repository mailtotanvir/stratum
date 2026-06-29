from fastapi import APIRouter

from app.models.session_agent_execution_projection import (
    SessionAgentExecutionProjection,
)
from app.services.session_agent_execution_projection_service import (
    session_agent_execution_projection_service,
)


router = APIRouter()


@router.get("/runtime/sessions/{runtime_session_id}/agent-executions")
def get_session_agent_executions(
    runtime_session_id: str,
) -> SessionAgentExecutionProjection:
    return session_agent_execution_projection_service.get_projection(
        runtime_session_id
    )
