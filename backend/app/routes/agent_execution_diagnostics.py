from fastapi import APIRouter

from app.models.agent_execution_diagnostics import AgentExecutionDiagnostics
from app.services.agent_execution_diagnostics_service import (
    agent_execution_diagnostics_service,
)


router = APIRouter()


@router.get("/runtime/agent-execution/diagnostics")
def get_agent_execution_diagnostics() -> AgentExecutionDiagnostics:
    return agent_execution_diagnostics_service.get_diagnostics()
